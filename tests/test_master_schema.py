# tests/test_master_schema.py
import sqlite3
from webapp.api.masters.schema import init_master_db, MASTER_TABLES


def _mem():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_init_master_db_creates_all_tables():
    conn = _mem()
    init_master_db(conn)
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert MASTER_TABLES <= names


def test_init_master_db_is_idempotent():
    conn = _mem()
    init_master_db(conn)
    init_master_db(conn)  # must not raise (IF NOT EXISTS)


def test_master_set_parent_fk_and_iso_created_at():
    conn = _mem()
    init_master_db(conn)
    conn.execute(
        "INSERT INTO master_set(name,note,created_at,created_by,parent_set_id)"
        " VALUES('現行','seed','2026-06-29T00:00:00',?,NULL)", ("kohei",))
    row = conn.execute("SELECT * FROM master_set").fetchone()
    assert row["parent_set_id"] is None
    assert row["created_at"] == "2026-06-29T00:00:00"  # ISO 8601


def test_file_profile_columns_present():
    conn = _mem()
    init_master_db(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(master_file_profile)")}
    assert {"master_set_id", "logical_name", "filename", "has_bom",
            "newline", "trailing_newline", "header_text", "format_json"} <= cols
