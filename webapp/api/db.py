import os
import sqlite3

from webapp.api.config import settings
from webapp.api.masters.schema import init_master_db

SCHEMA = """
CREATE TABLE IF NOT EXISTS rosters (
  id INTEGER PRIMARY KEY, job_id TEXT, year INT NOT NULL, month INT NOT NULL,
  target_holidays INT NOT NULL, data_dir TEXT NOT NULL, master_set_id INT,
  staff_json TEXT NOT NULL, daily_needs_json TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN('draft','confirmed')),
  version INT NOT NULL DEFAULT 0, edit_cursor INT NOT NULL DEFAULT 0,
  created_by TEXT, created_at TEXT NOT NULL, confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS roster_assignments (
  id INTEGER PRIMARY KEY,
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  staff_id TEXT NOT NULL, date TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN('day','night','oncall','request')),
  location_or_role TEXT, symbol TEXT, locked INT NOT NULL DEFAULT 0,
  UNIQUE(roster_id,staff_id,date,kind,location_or_role)
);
CREATE INDEX IF NOT EXISTS ix_ra_roster_date  ON roster_assignments(roster_id,date);
CREATE INDEX IF NOT EXISTS ix_ra_roster_staff ON roster_assignments(roster_id,staff_id);
CREATE TABLE IF NOT EXISTS roster_meta (
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  staff_id TEXT NOT NULL, off_count REAL NOT NULL DEFAULT 0,
  daikyu_count REAL NOT NULL DEFAULT 0, stats_json TEXT NOT NULL,
  PRIMARY KEY(roster_id,staff_id)
);
CREATE TABLE IF NOT EXISTS roster_edits (
  id INTEGER PRIMARY KEY,
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  seq INT NOT NULL, user_id TEXT, at TEXT NOT NULL,
  op TEXT NOT NULL CHECK(op IN('assign','unassign','move','toggle_lock','set_symbol','resolve')),
  payload_json TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
  undone INT NOT NULL DEFAULT 0, UNIQUE(roster_id,seq)
);
CREATE INDEX IF NOT EXISTS ix_re_roster_seq ON roster_edits(roster_id,seq);
"""


def connect(path: str) -> sqlite3.Connection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # check_same_thread=False: FastAPI runs sync endpoints in a threadpool, so a
    # per-request (or test-shared) connection is touched from a worker thread.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    # P3a: additive master-management tables (does not touch roster tables).
    init_master_db(conn)


def get_db():
    """FastAPI dependency: one connection per request (overridable in tests)."""
    conn = connect(settings.db_path)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()
