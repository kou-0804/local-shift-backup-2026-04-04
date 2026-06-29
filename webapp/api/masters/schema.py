"""SQLite schema for the master-management store (P3a).

Additive to the existing roster tables in ``webapp/api/db.py``. A ``master_set``
row is one immutable bundle of the eight on-disk master CSVs; each per-master
table carries ``master_set_id`` + ``row_order`` (CSV line order is load-bearing:
技師マスタ drives Excel row order; section-B power-balance rows are additive).
``master_file_profile`` carries the per-file byte-fidelity descriptor so the
serializer can rebuild byte-identical CSVs from structured data.
"""
import sqlite3

# Every table the master store owns. Tests assert this set is a subset of the
# tables present after init_master_db (proves the DDL created them all).
MASTER_TABLES = {
    "master_set", "ms_staff", "ms_skill_row", "ms_skill_cell", "ms_location",
    "ms_power_balance", "ms_special_rule", "ms_training", "ms_night_quota",
    "ms_night_override", "ms_holiday_target", "master_file_profile",
    "requests_import", "request_row",
}

MASTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS master_set (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT,
  parent_set_id INTEGER REFERENCES master_set(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ms_staff (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  tech_id TEXT, name TEXT, gender TEXT, experience_years INTEGER,
  night_ok TEXT, status TEXT, note TEXT, oncall_ok TEXT
);

CREATE TABLE IF NOT EXISTS ms_skill_row (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  tech_id TEXT, name TEXT
);

CREATE TABLE IF NOT EXISTS ms_skill_cell (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  tech_id TEXT, loc_code TEXT, rank TEXT
);

CREATE TABLE IF NOT EXISTS ms_location (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  loc_code TEXT, loc_name TEXT, category TEXT,
  mon TEXT, tue TEXT, wed TEXT, thu TEXT, fri TEXT, sat TEXT, sun TEXT,
  gender_constraint TEXT, display_order TEXT, active TEXT
);

CREATE TABLE IF NOT EXISTS ms_power_balance (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  loc_code TEXT, min_rank TEXT, min_count TEXT, cd_cap TEXT, d_solo_ban TEXT
);

CREATE TABLE IF NOT EXISTS ms_special_rule (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  rule_id TEXT, loc_code TEXT, weekday TEXT, week TEXT, required_count TEXT,
  rank_cond TEXT, rank_count TEXT, source_loc TEXT, source_rank TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS ms_training (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  modality TEXT,
  instructor_text TEXT, trainee_text TEXT, display_name TEXT,
  instructor_ids_json TEXT, trainee_ids_json TEXT, rank_a_only INTEGER
);

CREATE TABLE IF NOT EXISTS ms_night_quota (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  year_month TEXT, tech_id TEXT, name TEXT, count INTEGER
);

CREATE TABLE IF NOT EXISTS ms_night_override (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  sname TEXT, tech_id TEXT,
  night_mr TEXT, night_cath TEXT, night_angio TEXT, qual_code TEXT
);

CREATE TABLE IF NOT EXISTS ms_holiday_target (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  row_order INTEGER NOT NULL,
  year_month TEXT, holiday_count INTEGER
);

CREATE TABLE IF NOT EXISTS master_file_profile (
  id INTEGER PRIMARY KEY,
  master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE,
  logical_name TEXT NOT NULL,
  filename TEXT NOT NULL,
  has_bom INTEGER NOT NULL,
  newline TEXT NOT NULL,
  trailing_newline INTEGER NOT NULL,
  header_text TEXT,
  format_json TEXT,
  UNIQUE(master_set_id, logical_name)
);

CREATE TABLE IF NOT EXISTS requests_import (
  id INTEGER PRIMARY KEY,
  year_month TEXT,
  source_filename TEXT,
  imported_at TEXT,
  imported_by TEXT,
  raw_blob BLOB,
  has_bom INTEGER,
  newline TEXT,
  trailing_newline INTEGER
);

CREATE TABLE IF NOT EXISTS request_row (
  id INTEGER PRIMARY KEY,
  import_id INTEGER NOT NULL REFERENCES requests_import(id) ON DELETE CASCADE,
  tech_id_resolved TEXT, date TEXT, symbol TEXT, raw_rsname TEXT, resolve_status TEXT
);

CREATE INDEX IF NOT EXISTS ix_ms_staff_set        ON ms_staff(master_set_id, row_order);
CREATE INDEX IF NOT EXISTS ix_ms_skill_cell_set   ON ms_skill_cell(master_set_id, tech_id);
CREATE INDEX IF NOT EXISTS ix_ms_pb_set           ON ms_power_balance(master_set_id, loc_code);
CREATE INDEX IF NOT EXISTS ix_request_row_import  ON request_row(import_id);
"""


def init_master_db(conn: sqlite3.Connection) -> None:
    """Create every master-store table (idempotent via IF NOT EXISTS)."""
    conn.executescript(MASTER_SCHEMA)
    conn.commit()
