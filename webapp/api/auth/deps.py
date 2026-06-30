"""FastAPI auth dependencies.

``current_user`` resolves the caller from the ``session`` cookie OR an
``Authorization: Bearer`` header (CLI/tests), verifies the HMAC token, loads the
user, and raises 401 on any failure. ``require_role(*roles)`` builds a dependency
that 403s when the caller's role is not allowed.

Tests run authenticated by overriding ``current_user`` (see tests/conftest.py).
Because every ``require_role`` gate depends on ``current_user``, that single
override authenticates the whole existing suite as admin.
"""
from fastapi import Depends, HTTPException, Request

from webapp.api.db import get_db
from webapp.api.auth import service
from webapp.api.auth.tokens import resolve_secret, verify_token, TokenError


def _extract_token(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.cookies.get("session")


def current_user(request: Request, conn=Depends(get_db)) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        claims = verify_token(token, resolve_secret())
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = service.get_user(conn, int(claims.get("uid", -1)))
    if user is None or user["disabled"]:
        raise HTTPException(status_code=401, detail="user not found or disabled")
    return user


def require_role(*roles):
    """Return a dependency that allows only the given roles (403 otherwise)."""
    allowed = set(roles)

    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return checker
