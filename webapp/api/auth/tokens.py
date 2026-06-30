"""Stdlib HMAC-signed session tokens (no JWT library).

Wire form: ``b64url(payload) + "." + b64url(HMAC_SHA256(secret, b64url(payload)))``
where ``payload = {"uid":..,"role":..,"exp":<epoch>}``. The signature is verified
BEFORE the payload is trusted (compare_digest), then expiry is checked. Any
failure raises ``TokenError`` — never a silent bypass.
"""
import base64
import hashlib
import hmac
import json
import os
import time

from webapp.api.config import settings


class TokenError(Exception):
    """Raised on any token failure: bad shape, bad signature, or expired."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign_token(claims: dict, secret: bytes, ttl_seconds: int) -> str:
    payload = {**claims, "exp": int(time.time()) + ttl_seconds}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64url_encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str, secret: bytes) -> dict:
    try:
        body, sig = token.split(".")
    except (ValueError, AttributeError):
        raise TokenError("malformed token")
    expected = _b64url_encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise TokenError("bad signature")
    try:
        payload = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        raise TokenError("undecodable payload")
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise TokenError("expired")
    return payload


def resolve_secret() -> bytes:
    """Resolve the HMAC secret.

    Priority: SHIFT_AUTH_SECRET env -> a persisted ``webapp_data/.auth_secret``
    file (auto-created with 32 random bytes on first run). The file keeps sessions
    valid across restarts without committing a secret. On Windows the directory
    ACL is the real guard (chmod is best-effort).
    """
    if settings.auth_secret_env:
        return settings.auth_secret_env.encode("utf-8")
    path = settings.auth_secret_path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            data = fh.read().strip()
            if data:
                return data
    import secrets as _secrets
    new_secret = _secrets.token_bytes(32).hex().encode("ascii")
    with open(path, "wb") as fh:
        fh.write(new_secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows: directory ACL is the guard (documented in deploy/README).
    return new_secret
