"""P4b: additive ``users`` table. Mirrors the ``init_master_db`` pattern —
called from ``webapp/api/db.py::init_db``; never touches roster tables.
"""
import sqlite3

USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  login_id TEXT NOT NULL UNIQUE,
  name TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN('admin','editor','viewer')),
  created_at TEXT NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0
);
"""


def init_auth_db(conn: sqlite3.Connection) -> None:
    conn.executescript(USERS_DDL)
    conn.commit()
