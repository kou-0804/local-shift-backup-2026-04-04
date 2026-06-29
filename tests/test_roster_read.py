from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments={1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={"T001": 9},
        validation_errors=[], daily_location_needs={1: {"CT": 1}})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_get_roster_returns_grid_stats_warnings_version(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).get(f"/rosters/{rid}")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 0
        assert any(row["staff_id"] == "T001" for row in body["grid"]["rows"])
        assert "warnings" in body and "coverage" in body["warnings"]
    finally:
        app.dependency_overrides.clear()


def test_get_roster_grid_only(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).get(f"/rosters/{rid}/grid")
        assert r.status_code == 200
        assert "rows" in r.json() and "warnings" not in r.json()
    finally:
        app.dependency_overrides.clear()


def test_get_missing_roster_404(tmp_path):
    conn, _ = _seed(tmp_path)
    try:
        assert _client(conn).get("/rosters/9999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_contract_fields_year_month_holidays(tmp_path):
    # P2d client builds ISO dates from year/month and shades public holidays.
    conn, rid = _seed(tmp_path)
    try:
        body = _client(conn).get(f"/rosters/{rid}").json()
        # top-level year/month on the roster response
        assert body["year"] == 2026 and body["month"] == 6
        # grid carries year/month + holidays (ISO strings)
        grid = body["grid"]
        assert grid["year"] == 2026 and grid["month"] == 6
        assert isinstance(grid["holidays"], list)
        # 2026-06: holidays = Sundays only (no 祝日 in June). 7/14/21/28 are Sundays.
        assert "2026-06-07" in grid["holidays"]
        assert "2026-06-14" in grid["holidays"]
        # Saturdays are NOT public holidays
        assert "2026-06-06" not in grid["holidays"]
        # rows keyed by staff_id (NOT sid)
        assert all("staff_id" in row for row in grid["rows"])
        # grid-only endpoint also exposes holidays
        g = _client(conn).get(f"/rosters/{rid}/grid").json()
        assert "holidays" in g
    finally:
        app.dependency_overrides.clear()
