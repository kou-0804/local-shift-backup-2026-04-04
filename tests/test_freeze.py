from types import SimpleNamespace

from shift_scheduler.src.models.schedule_result import ScheduleResult
from webapp.api.db import connect, init_db
from webapp.api.rosters import freeze_roster, roster_to_dicts


def _conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    return c


def _result():
    return ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}, {"id": "T002", "name": "乙"}],
        day_assignments={1: {"CT": ["T001"], "休": ["T002"]}, 2: {"○": ["T001"]}},
        night_assignments={1: ["T001"]},
        requests={1: {"T002": "☆"}},
        on_call_assignments={1: {"第1拘束": "T001"}},
        daikyu_counts={"T001": 0}, off_counts={"T001": 9, "T002": 10},
        validation_errors=["ignored"],
        daily_location_needs={1: {"CT": 1}},
    )


def _techs():
    return [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=True),
            SimpleNamespace(id="T002", name="乙", status="在籍", note="核医学", night_hb=False)]


def test_freeze_creates_rows_and_meta(tmp_path):
    conn = _conn(tmp_path)
    rid = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                        data_dir="d", target_holidays=9)
    kinds = [r["kind"] for r in conn.execute(
        "SELECT kind FROM roster_assignments WHERE roster_id=?", (rid,))]
    assert kinds.count("day") == 3       # CT, 休, ○
    assert kinds.count("night") == 1
    assert kinds.count("request") == 1
    assert kinds.count("oncall") == 1
    meta = {r["staff_id"]: r for r in conn.execute(
        "SELECT * FROM roster_meta WHERE roster_id=?", (rid,))}
    assert meta["T002"]["off_count"] == 10
    # validation_errors NOT frozen anywhere
    hdr = conn.execute("SELECT * FROM rosters WHERE id=?", (rid,)).fetchone()
    assert hdr["target_holidays"] == 9 and hdr["version"] == 0 and hdr["edit_cursor"] == 0


def test_freeze_idempotent_per_job(tmp_path):
    conn = _conn(tmp_path)
    a = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                      data_dir="d", target_holidays=9)
    b = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                      data_dir="d", target_holidays=9)
    assert a == b
    n = conn.execute("SELECT COUNT(*) FROM rosters").fetchone()[0]
    assert n == 1


def test_roster_to_dicts_round_trip(tmp_path):
    conn = _conn(tmp_path)
    rid = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                        data_dir="d", target_holidays=9)
    d = roster_to_dicts(conn, rid)
    assert d["day_assignments"][1]["CT"] == ["T001"]
    assert d["day_assignments"][1]["休"] == ["T002"]
    assert d["night_assignments"][1] == ["T001"]
    assert d["requests"][1]["T002"] == "☆"
    assert d["on_call_assignments"][1]["第1拘束"] == "T001"
    assert d["daily_location_needs"][1]["CT"] == 1
    # enriched staff carry note/night_hb for build_grid/recompute_stats
    by_id = {t.id: t for t in d["technicians"]}
    assert by_id["T002"].note == "核医学" and by_id["T001"].night_hb is True
