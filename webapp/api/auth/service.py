"""User CRUD + authentication over the ``users`` table.

The single closed role set is ``{admin, editor, viewer}`` — validated here, in
the DB CHECK, in ``require_role``, and mirrored by the frontend ``roles.ts``.
``authenticate`` returns a public dict (no password_hash) or ``None``.
"""
import sqlite3
from datetime import datetime, timezone

from webapp.api.auth.passwords import hash_password, verify_password

ROLES = ("admin", "editor", "viewer")
MIN_PASSWORD_LEN = 8


class DuplicateUser(Exception):
    """Raised when login_id already exists."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "login_id": row["login_id"],
        "name": row["name"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
    }


def create_user(conn, *, login_id: str, password: str, role: str, name: str = "") -> int:
    if role not in ROLES:
        raise ValueError(f"invalid role {role!r}; must be one of {ROLES}")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    try:
        cur = conn.execute(
            "INSERT INTO users(login_id, name, password_hash, role, created_at, disabled) "
            "VALUES(?,?,?,?,?,0)",
            (login_id, name, hash_password(password), role, _now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicateUser(f"login_id {login_id!r} already exists") from exc
    return cur.lastrowid


def authenticate(conn, login_id: str, password: str):
    row = conn.execute(
        "SELECT * FROM users WHERE login_id=? AND disabled=0", (login_id,)
    ).fetchone()
    if row is None:
        # Still hash to keep timing roughly uniform between missing/wrong user.
        verify_password(password, "pbkdf2_sha256$1$00$00")
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _public(row)


def get_user(conn, uid: int):
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return _public(row) if row is not None else None


def list_users(conn) -> list:
    return [_public(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]


def set_password(conn, uid: int, password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                 (hash_password(password), uid))
    conn.commit()


def set_disabled(conn, uid: int, disabled: bool) -> None:
    conn.execute("UPDATE users SET disabled=? WHERE id=?", (1 if disabled else 0, uid))
    conn.commit()


def count_users(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
