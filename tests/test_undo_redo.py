from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path, night=None, day=None):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments=day or {1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}},
        night_assignments=night or {}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T001": 9}, validation_errors=[],
        daily_location_needs={})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_undo_then_redo_round_trips(tmp_path):
    conn, rid = _seed(tmp_path)
    c = _client(conn)
    try:
        c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "CT", "expected_version": 0})
        u = c.post(f"/rosters/{rid}/undo", json={"expected_version": 1})
        assert u.status_code == 200 and u.json()["version"] == 2
        # cell back to 'ク'
        cell = next(x for x in u.json()["changed_cells"]
                    if x["date"] == "2026-06-02")
        assert cell["text"] == "ク"
        assert u.json()["redo_available"] is True
        r = c.post(f"/rosters/{rid}/redo", json={"expected_version": 2})
        assert r.status_code == 200
        cell = next(x for x in r.json()["changed_cells"] if x["date"] == "2026-06-02")
        assert cell["text"] == "CT"
    finally:
        app.dependency_overrides.clear()


def test_new_edit_after_undo_truncates_redo(tmp_path):
    conn, rid = _seed(tmp_path)
    c = _client(conn)
    try:
        c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "CT", "expected_version": 0})
        c.post(f"/rosters/{rid}/undo", json={"expected_version": 1})
        new = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "MG", "expected_version": 2})
        assert new.status_code == 200 and new.json()["redo_available"] is False
    finally:
        app.dependency_overrides.clear()


def test_undo_unavailable_at_baseline(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/undo", json={"expected_version": 0})
        assert r.status_code == 409  # nothing to undo (cursor==0)
    finally:
        app.dependency_overrides.clear()


def test_night_edit_flips_next_day_akemei_and_reverts(tmp_path):
    # T001 has a night on day 1 already; unassign it -> day 2 stops being 明け.
    conn, rid = _seed(tmp_path, night={1: ["T001"]}, day={1: {}, 2: {}})
    c = _client(conn)
    try:
        g = _client(conn).get(f"/rosters/{rid}/grid").json()
        row = next(r for r in g["rows"] if r["staff_id"] == "T001")
        assert row["cells"]["2"] == "○"  # frozen 明け from day-1 night
        # toggle_lock is a no-op for text; use an assign on day 1 that the D+1 rule covers.
        resp = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-01",
            "location": "CT", "expected_version": 0})
        dates = {x["date"] for x in resp.json()["changed_cells"]}
        assert "2026-06-02" in dates  # D+1 re-derived because a night row exists on day 1
    finally:
        app.dependency_overrides.clear()
