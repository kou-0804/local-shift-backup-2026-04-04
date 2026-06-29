from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def test_freeze_read_edit_undo_flow(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments={1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}},
        night_assignments={}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T001": 9}, validation_errors=[],
        daily_location_needs={2: {"ク": 1}})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    app.dependency_overrides[api_main.get_db] = lambda: conn
    try:
        c = TestClient(app)
        assert c.get(f"/rosters/{rid}").json()["version"] == 0
        e = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-03",
            "location": "MG", "expected_version": 0}).json()
        assert e["version"] == 1
        assert c.get(f"/rosters/{rid}").json()["version"] == 1
        u = c.post(f"/rosters/{rid}/undo", json={"expected_version": 1}).json()
        assert u["version"] == 2 and u["undo_available"] is False
    finally:
        app.dependency_overrides.clear()
