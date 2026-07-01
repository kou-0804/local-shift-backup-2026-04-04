"""GET /masters/requests/{year}/{month} — 予定申請 import status for the
勤務表作成 page. Read-only; shows whether the month's CSV is loaded."""
from fastapi.testclient import TestClient

from webapp.api.db import connect, init_db, get_db
from webapp.api.main import app


def _seed(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO requests_import(year_month,source_filename,imported_at) "
        "VALUES('2026-07','予定申請.csv','2026-07-01T09:00:00')")
    imp_id = cur.lastrowid
    conn.execute(
        "INSERT INTO request_row(import_id,tech_id_resolved,date,symbol) "
        "VALUES(?,?,?,?)", (imp_id, "T001", "2026-07-03", "◆"))
    conn.commit()
    return conn


def _client(conn):
    app.dependency_overrides[get_db] = lambda: conn
    return TestClient(app)


def test_requests_status_imported(tmp_path):
    conn = _seed(tmp_path)
    try:
        body = _client(conn).get("/masters/requests/2026/7").json()
        assert body["imported"] is True
        assert body["row_count"] == 1
        assert body["year"] == 2026 and body["month"] == 7
        assert body["source_filename"] == "予定申請.csv"
        assert body["imported_at"]
    finally:
        app.dependency_overrides.clear()


def test_requests_status_not_imported(tmp_path):
    conn = _seed(tmp_path)
    try:
        body = _client(conn).get("/masters/requests/2026/8").json()
        assert body["imported"] is False
        assert body["row_count"] == 0
        assert body["import_id"] is None
    finally:
        app.dependency_overrides.clear()
