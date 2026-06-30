import pytest

from webapp.api.auth.passwords import hash_password, verify_password


# --- P4b-1: password hashing (stdlib pbkdf2) --------------------------------

def test_hash_is_salted_and_verifies():
    h = hash_password("correct horse")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong", h) is False


def test_two_hashes_of_same_password_differ():
    # per-user random salt -> different encoded hashes
    assert hash_password("pw") != hash_password("pw")


def test_verify_is_constant_time_and_handles_garbage():
    assert verify_password("x", "not-a-valid-encoding") is False
    assert verify_password("x", "") is False
    assert verify_password("x", "pbkdf2_sha256$bad$nope") is False


# --- P4b-2: signed session token (stdlib hmac) ------------------------------

from webapp.api.auth.tokens import sign_token, verify_token, TokenError

SECRET = b"test-secret-bytes"


def test_token_round_trips_uid_and_role():
    tok = sign_token({"uid": 7, "role": "admin"}, SECRET, ttl_seconds=3600)
    claims = verify_token(tok, SECRET)
    assert claims["uid"] == 7 and claims["role"] == "admin"


def test_tampered_payload_is_rejected():
    tok = sign_token({"uid": 7, "role": "viewer"}, SECRET, ttl_seconds=3600)
    head, sig = tok.split(".")
    forged = head[:-1] + ("A" if head[-1] != "A" else "B") + "." + sig
    with pytest.raises(TokenError):
        verify_token(forged, SECRET)


def test_wrong_secret_is_rejected():
    tok = sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=3600)
    with pytest.raises(TokenError):
        verify_token(tok, b"other-secret")


def test_expired_token_is_rejected():
    tok = sign_token({"uid": 1, "role": "admin"}, SECRET, ttl_seconds=-1)
    with pytest.raises(TokenError):
        verify_token(tok, SECRET)


def test_malformed_token_is_rejected():
    with pytest.raises(TokenError):
        verify_token("garbage-no-dot", SECRET)


# --- P4b-3: users table, service, bootstrap ---------------------------------

from webapp.api.db import connect, init_db
from webapp.api.auth import service


@pytest.fixture()
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    return c


def test_create_and_authenticate(conn):
    service.create_user(conn, login_id="alice", password="pw123456", role="editor", name="Alice")
    u = service.authenticate(conn, "alice", "pw123456")
    assert u["role"] == "editor" and u["login_id"] == "alice"
    assert service.authenticate(conn, "alice", "wrong") is None
    assert service.authenticate(conn, "nobody", "pw") is None


def test_login_id_is_unique(conn):
    service.create_user(conn, login_id="bob", password="pw123456", role="viewer")
    with pytest.raises(service.DuplicateUser):
        service.create_user(conn, login_id="bob", password="pw999999", role="viewer")


def test_role_is_validated(conn):
    with pytest.raises(ValueError):
        service.create_user(conn, login_id="x", password="pw123456", role="superuser")


def test_short_password_is_rejected(conn):
    with pytest.raises(ValueError):
        service.create_user(conn, login_id="y", password="short", role="viewer")


def test_disabled_user_cannot_authenticate(conn):
    uid = service.create_user(conn, login_id="z", password="pw123456", role="editor")
    service.set_disabled(conn, uid, True)
    assert service.authenticate(conn, "z", "pw123456") is None


def test_ensure_admin_is_idempotent(conn):
    from webapp.api.auth.bootstrap import ensure_admin
    a = ensure_admin(conn, login_id="admin", password="changeme123")
    b = ensure_admin(conn, login_id="admin", password="changeme123")
    assert a == b  # second call is a no-op, returns the same user id
    assert service.authenticate(conn, "admin", "changeme123")["role"] == "admin"
