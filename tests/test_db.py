import sqlite3

from webapp.api.db import connect, init_db


def test_init_db_creates_four_tables(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"rosters", "roster_assignments", "roster_meta", "roster_edits"} <= names


def test_foreign_keys_and_cascade(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO rosters(year,month,target_holidays,data_dir,staff_json,created_at)"
        " VALUES(2026,6,9,'d','[]','2026-06-29T00:00:00')")
    rid = cur.lastrowid
    conn.execute(
        "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,location_or_role)"
        " VALUES(?,?,?,?,?)", (rid, "T001", "2026-06-01", "day", "CT"))
    conn.commit()
    conn.execute("DELETE FROM rosters WHERE id=?", (rid,))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM roster_assignments").fetchone()[0]
    assert n == 0  # ON DELETE CASCADE with PRAGMA foreign_keys=ON


def test_status_check_constraint(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rosters(year,month,target_holidays,data_dir,staff_json,"
            "created_at,status) VALUES(2026,6,9,'d','[]','t','bogus')")
