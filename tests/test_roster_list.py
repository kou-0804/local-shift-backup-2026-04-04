"""GET /rosters — the roster index the SPA shows when no ?rid= is selected.

Read-only listing; never touches the materialize→freeze→render path, so the
byte-identical roundtrip is unaffected. Newest month first so the picker's top
row is the roster a user most likely wants.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _result(year, month):
    return ScheduleResult(
        year=year, month=month, staff=[{"id": "T001", "name": "甲"}],
        day_assignments={1: {"CT": ["T001"]}}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={"T001": 9},
        validation_errors=[], daily_location_needs={1: {"CT": 1}})


def _seed_two(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid_may = freeze_roster(conn, job_id="jm", result=_result(2026, 5), technicians=techs,
                            data_dir="d", target_holidays=9)
    rid_jun = freeze_roster(conn, job_id="jj", result=_result(2026, 6), technicians=techs,
                            data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid_may, rid_jun


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_list_rosters_newest_month_first_with_fields(tmp_path):
    conn, rid_may, rid_jun = _seed_two(tmp_path)
    try:
        r = _client(conn).get("/rosters")
        assert r.status_code == 200
        body = r.json()
        assert [row["id"] for row in body] == [rid_jun, rid_may]
        top = body[0]
        assert top["year"] == 2026 and top["month"] == 6
        assert top["status"] == "draft"
        assert "created_at" in top and top["created_at"]
        assert "confirmed_at" in top  # present (null until confirmed)
    finally:
        app.dependency_overrides.clear()


def test_list_rosters_empty(tmp_path):
    conn = connect(str(tmp_path / "empty.db"))
    init_db(conn)
    try:
        r = _client(conn).get("/rosters")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
