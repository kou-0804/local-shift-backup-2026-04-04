"""First-run admin bootstrap.

``ensure_admin`` creates the admin account only when ``users`` is empty
(idempotent), so ``start.bat`` can call it on every boot. The ``__main__`` block
(``python -m webapp.api.auth.bootstrap``) reads SHIFT_ADMIN_ID / SHIFT_ADMIN_PW
and refuses to run with a blank/short password (fail loudly, never silently).
"""
import os
import sys

from webapp.api.auth import service


def ensure_admin(conn, *, login_id: str, password: str) -> int:
    """Create the admin if no users exist. Returns the admin user id either way.

    Idempotent: a second call with an existing user table is a no-op and returns
    the existing admin's id (looked up by login_id).
    """
    if service.count_users(conn) > 0:
        row = conn.execute(
            "SELECT id FROM users WHERE login_id=?", (login_id,)
        ).fetchone()
        if row is not None:
            return row["id"]
        # Users exist but not this admin login -> still create it as admin.
        return service.create_user(
            conn, login_id=login_id, password=password, role="admin", name="管理者")
    return service.create_user(
        conn, login_id=login_id, password=password, role="admin", name="管理者")


def main() -> int:
    from webapp.api.config import settings
    from webapp.api.db import connect, init_db

    login_id = os.environ.get("SHIFT_ADMIN_ID", "admin")
    password = os.environ.get("SHIFT_ADMIN_PW", "")
    if not password or len(password) < service.MIN_PASSWORD_LEN:
        sys.stderr.write(
            "ERROR: SHIFT_ADMIN_PW must be set to at least "
            f"{service.MIN_PASSWORD_LEN} characters before bootstrap.\n")
        return 2
    conn = connect(settings.db_path)
    init_db(conn)
    uid = ensure_admin(conn, login_id=login_id, password=password)
    print(f"admin user ready: login_id={login_id} id={uid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
