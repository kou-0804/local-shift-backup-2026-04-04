"""P4c: additive ``archives`` table — immutable confirmed-month Excel snapshots.
Called from ``webapp/api/db.py::init_db``; never touches roster columns (the
``rosters`` table already has status/confirmed_at).
"""
import sqlite3

ARCHIVES_DDL = """
CREATE TABLE IF NOT EXISTS archives (
  id INTEGER PRIMARY KEY,
  roster_id INTEGER NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  xlsx_bytes BLOB NOT NULL,
  checksum TEXT NOT NULL,
  archived_at TEXT NOT NULL,
  archived_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_arch_year_month ON archives(year, month);
"""


def init_archive_db(conn: sqlite3.Connection) -> None:
    conn.executescript(ARCHIVES_DDL)
    conn.commit()
