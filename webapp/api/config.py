import os
import sqlite3
from typing import Optional


class Settings:
    # P1: masters are the on-disk CSVs; P3 adds a SQLite master store materialized
    # back to a byte-identical temp data_dir at generation time.
    data_dir: str = os.environ.get("SHIFT_DATA_DIR", "shift_scheduler/data")
    # P2a-2: roster persistence DB (frozen rosters, edits, undo/redo).
    db_path: str = os.environ.get("SHIFT_DB_PATH", "webapp_data/shift.db")
    # P3: base dir for per-job materialized data dirs (None -> system temp).
    temp_base: Optional[str] = os.environ.get("SHIFT_TEMP_BASE") or None
    # P3: explicit override for which master_set generation should use. When unset,
    # resolve_default_master_set_id() falls back to the seeded set in the DB.
    master_set_id_env: Optional[str] = os.environ.get("SHIFT_MASTER_SET_ID") or None
    # P4a: built SPA directory (frontend/dist). Unset in dev (Vite serves the SPA
    # via its proxy); set in prod so the single uvicorn process serves SPA + API.
    frontend_dist: Optional[str] = os.environ.get("SHIFT_FRONTEND_DIST") or None
    # P4b: HMAC session-token secret + TTL + the auth-secret fallback file.
    auth_secret_env: Optional[str] = os.environ.get("SHIFT_AUTH_SECRET") or None
    auth_secret_path: str = os.environ.get(
        "SHIFT_AUTH_SECRET_PATH", "webapp_data/.auth_secret")
    token_ttl_seconds: int = int(os.environ.get("SHIFT_TOKEN_TTL", str(12 * 3600)))


settings = Settings()


def resolve_default_master_set_id(conn: sqlite3.Connection) -> Optional[int]:
    """Resolve which master_set generation should use.

    Priority: explicit SHIFT_MASTER_SET_ID env override, else the seeded "現行"
    set (lowest id), else any earliest master_set, else None (no master store
    seeded -> caller falls back to the on-disk data_dir, preserving P1/P2 behaviour).
    """
    if settings.master_set_id_env:
        try:
            return int(settings.master_set_id_env)
        except ValueError:
            pass
    row = conn.execute(
        "SELECT id FROM master_set ORDER BY (name='現行') DESC, id ASC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return row[0] if not isinstance(row, sqlite3.Row) else row["id"]
