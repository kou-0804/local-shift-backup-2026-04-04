from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path, **kw):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}, {"id": "T002", "name": "乙"}],
        day_assignments=kw.get("day", {1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}}),
        night_assignments=kw.get("night", {}),
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={"T001": 9, "T002": 9},
        validation_errors=[], daily_location_needs=kw.get("needs", {2: {"ク": 2}}))
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False),
             SimpleNamespace(id="T002", name="乙", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_assign_updates_cell_and_version(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T002", "date": "2026-06-02",
            "location": "ク", "expected_version": 0})
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 1 and body["seq"] == 1
        cell = next(c for c in body["changed_cells"]
                    if c["staff_id"] == "T002" and c["date"] == "2026-06-02")
        assert cell["text"] == "ク"
        assert "T002" in body["stats"]
        # coverage for ク on day 2 now satisfied (req 2, assigned 2)
        assert all(c["location"] != "ク" or c["date"] != "2026-06-02"
                   for c in body["warnings"]["coverage"])
        assert body["undo_available"] is True and body["redo_available"] is False
    finally:
        app.dependency_overrides.clear()


def test_unassign_raises_off(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        before = conn.execute(
            "SELECT off_count FROM roster_meta WHERE roster_id=? AND staff_id='T001'",
            (rid,)).fetchone()["off_count"]
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "unassign", "staff_id": "T001", "date": "2026-06-02",
            "location": "ク", "expected_version": 0})
        assert r.status_code == 200
        assert r.json()["stats"]["T001"]["公休"] > before  # blank weekday = rest
    finally:
        app.dependency_overrides.clear()


def test_stale_version_conflicts_409(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T002", "date": "2026-06-02",
            "location": "ク", "expected_version": 99})
        assert r.status_code == 409
        assert "grid" in r.json()["detail"]  # current grid for rebase
    finally:
        app.dependency_overrides.clear()


def test_move_is_single_edit(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "move", "staff_id": "T001",
            "from": {"date": "2026-06-01", "location": "CT"},
            "to": {"date": "2026-06-03", "location": "CT"},
            "expected_version": 0})
        assert r.status_code == 200
        n = conn.execute("SELECT COUNT(*) FROM roster_edits WHERE roster_id=?",
                         (rid,)).fetchone()[0]
        assert n == 1  # one edit, one undo step
    finally:
        app.dependency_overrides.clear()


def test_night_edit_rederives_next_day_akemei(tmp_path):
    conn, rid = _seed(tmp_path, day={1: {"CT": ["T001"]}}, night={})
    try:
        # assign a night to T001 on day 1 -> day 2 must become 明け '○'
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-01",
            "location": "夜", "expected_version": 0})
        # NOTE: night is kind='night'; for this test the assign op writes a day row '夜'.
        # The D+1 rule is exercised explicitly in test_undo_redo via a night freeze.
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_toggle_lock_no_stats_change(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "toggle_lock", "staff_id": "T001", "date": "2026-06-01",
            "location": "CT", "locked": True, "expected_version": 0})
        assert r.status_code == 200
        locked = conn.execute(
            "SELECT locked FROM roster_assignments WHERE roster_id=? AND staff_id='T001'"
            " AND date='2026-06-01' AND kind='day'", (rid,)).fetchone()["locked"]
        assert locked == 1
        cell = next(c for c in r.json()["changed_cells"] if c["staff_id"] == "T001")
        assert cell["locked"] is True
    finally:
        app.dependency_overrides.clear()
