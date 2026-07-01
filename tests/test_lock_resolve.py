# tests/test_lock_resolve.py
"""P2b partial-lock re-solve tests.

Structure:
  * Task 1  — empty-lock byte-identity gate (slow, the keystone determinism contract).
  * Task 2  — pure lock_utils (fast, no solver).
  * Task 3-7 — real-solver lock injection / diagnostics (slow).
  * Task 8  — /resolve wiring (fast, mocked RUNNER).
  * Task 9  — end-to-end /resolve real solver (slow).

Slow tests derive their concrete (staff_id, loc, day) cells from a single
module-scoped baseline run (rather than hardcoding fragile tuples), so the
chosen cells are guaranteed skill-eligible / currently-assigned by construction.
"""
import json
import os
from datetime import date

import pytest

from main import run_schedule

DATA_DIR = "shift_scheduler/data"
GOLDEN = "tests/golden/2026-06_assignments.json"


def _canon(d):
    return json.loads(json.dumps(d, ensure_ascii=False, sort_keys=True))


# ===========================================================================
# Task 1 — Empty-lock byte-identity gate (the single most important test)
# ===========================================================================


@pytest.mark.slow
def test_empty_lock_set_is_byte_identical_to_today_and_golden():
    base = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    empty = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments={}).as_dict()
    none_ = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=None).as_dict()
    assert _canon(empty) == _canon(base)
    assert _canon(none_) == _canon(base)
    assert os.path.exists(GOLDEN), "golden snapshot missing"
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    assert _canon(empty) == _canon(expected)


@pytest.mark.slow
def test_empty_lock_does_not_leak_lock_fields_into_as_dict():
    r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments={})
    d = r.as_dict()
    assert "unlockable_locks" not in d and "lock_conflicts" not in d
    # The empty lock set must surface no diagnostics.
    assert r.unlockable_locks == [] and r.lock_conflicts == []


# ===========================================================================
# Task 2 — pure lock_utils (fast, no solver)
# ===========================================================================

from shift_scheduler.src.lock_utils import (  # noqa: E402
    validate_lock_set, reassert_locks, day_locks_from_rows, NIGHT_LOC, OFF_LOCS,
)


def test_validate_rejects_two_forced_locs_same_staff_day():
    la = {date(2026, 6, 10): {"force": {("T013", "CT"), ("T013", "病CT")}, "forbid": set()}}
    errs = validate_lock_set(la, daily_location_needs={})
    assert any("T013" in e and "2026-06-10" in e for e in errs)


def test_validate_rejects_forced_count_over_needs():
    la = {date(2026, 6, 10): {"force": {("T001", "MG"), ("T002", "MG")}, "forbid": set()}}
    needs = {10: {"MG": 1}}
    errs = validate_lock_set(la, daily_location_needs=needs)
    assert any("MG" in e for e in errs)


def test_validate_allows_off_lock_and_single_force():
    la = {date(2026, 6, 10): {"force": {("T013", "CT"), ("T020", "休")}, "forbid": set()}}
    assert validate_lock_set(la, daily_location_needs={10: {"CT": 3}}) == []


def test_validate_rejects_work_and_off_for_same_staff():
    la = {date(2026, 6, 10): {"force": {("T013", "CT"), ("T013", "休")}, "forbid": set()}}
    errs = validate_lock_set(la, daily_location_needs={})
    assert any("T013" in e for e in errs)


def test_validate_rejects_force_and_forbid_same_cell():
    la = {date(2026, 6, 10): {"force": {("T013", "CT")}, "forbid": {("T013", "CT")}}}
    errs = validate_lock_set(la, daily_location_needs={})
    assert any("force" in e and "forbid" in e for e in errs)


def test_day_locks_from_rows_builds_force_for_work_and_off():
    rows = [
        {"staff_id": "T013", "date": "2026-06-10", "kind": "day",
         "location_or_role": "CT", "locked": 1},
        {"staff_id": "T020", "date": "2026-06-10", "kind": "day",
         "location_or_role": None, "locked": 1},   # empty-cell sentinel = OFF
        {"staff_id": "T099", "date": "2026-06-10", "kind": "day",
         "location_or_role": "MG", "locked": 0},    # not locked -> ignored
    ]
    la = day_locks_from_rows(rows)
    d = date(2026, 6, 10)
    assert ("T013", "CT") in la[d]["force"]
    assert ("T020", "休") in la[d]["force"]
    assert all(sid != "T099" for sid, _ in la[d]["force"])


def test_reassert_locks_repositions_locked_staff():
    from shift_scheduler.src.models.assignment import DayAssignment
    from shift_scheduler.src.models.skill import SkillRank
    d = date(2026, 6, 10)
    rows = [DayAssignment(date=d, staff_id="T013", location_code="MG", rank=SkillRank.B)]
    la = {d: {"force": {("T013", "CT")}, "forbid": set()}}
    out = reassert_locks(rows, la, 2026, 6)
    cells = {(a.staff_id, a.location_code) for a in out if a.date == d}
    assert ("T013", "CT") in cells and ("T013", "MG") not in cells


def test_reassert_locks_empty_is_noop_identity():
    # determinism: empty/None lock set returns the SAME list object untouched.
    rows = [object()]
    assert reassert_locks(rows, {}, 2026, 6) is rows
    assert reassert_locks(rows, None, 2026, 6) is rows


def test_reassert_off_lock_becomes_kyu_row():
    from shift_scheduler.src.models.assignment import DayAssignment
    from shift_scheduler.src.models.skill import SkillRank
    d = date(2026, 6, 10)
    rows = [DayAssignment(date=d, staff_id="T013", location_code="CT", rank=SkillRank.B)]
    la = {d: {"force": {("T013", "○")}, "forbid": set()}}
    out = reassert_locks(rows, la, 2026, 6)
    cells = {(a.staff_id, a.location_code) for a in out if a.date == d}
    assert ("T013", "休") in cells and ("T013", "CT") not in cells


# ===========================================================================
# Task 8 — POST /rosters/{rid}/resolve wiring (fast, mocked RUNNER, no solver)
# ===========================================================================

import pytest as _pytest  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
import webapp.api.main as api_main  # noqa: E402
from webapp.api.db import connect, init_db  # noqa: E402
from webapp.api.main import app  # noqa: E402
from webapp.api.rosters import freeze_roster  # noqa: E402
from shift_scheduler.src.models.schedule_result import ScheduleResult  # noqa: E402


@_pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    yield c
    c.close()


@_pytest.fixture
def client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@_pytest.fixture
def seeded_roster(conn):
    """A 2-staff roster: T013->CT, T099->MG on 2026-06-16 (needs CT:3, MG:1)."""
    result = ScheduleResult(
        year=2026, month=6,
        staff=[{"id": "T013", "name": "甲"}, {"id": "T099", "name": "乙"}],
        day_assignments={16: {"CT": ["T013"], "MG": ["T099"]}},
        night_assignments={}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T013": 9, "T099": 9}, validation_errors=[],
        daily_location_needs={16: {"CT": 3, "MG": 1}})
    techs = [SimpleNamespace(id="T013", name="甲", status="在籍", note="", night_hb=False),
             SimpleNamespace(id="T099", name="乙", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="shift_scheduler/data", target_holidays=9)
    conn.commit()
    return rid


def _lock_t013_ct(client, rid):
    r = client.post(f"/rosters/{rid}/edits", json={
        "expected_version": 0, "op": "toggle_lock",
        "staff_id": "T013", "date": "2026-06-16", "location": "CT", "locked": True})
    assert r.status_code == 200, r.text
    return r.json()["version"]


def _day_row(conn, rid, sid):
    return conn.execute(
        "SELECT location_or_role,locked FROM roster_assignments WHERE roster_id=? "
        "AND staff_id=? AND date='2026-06-16' AND kind='day'", (rid, sid)).fetchone()


def test_resolve_keeps_locked_replaces_unlocked(client, conn, seeded_roster, monkeypatch):
    rid = seeded_roster
    ver = _lock_t013_ct(client, rid)

    def fake_runner(year, month, data_dir, *, locked_assignments=None, **kw):
        assert locked_assignments and date(2026, 6, 16) in locked_assignments
        assert ("T013", "CT") in locked_assignments[date(2026, 6, 16)]["force"]
        # locked CT[T013] preserved; unlocked T099 moved MG -> ク to prove replacement.
        return ScheduleResult(
            year=year, month=month,
            staff=[{"id": "T013", "name": "甲"}, {"id": "T099", "name": "乙"}],
            day_assignments={16: {"CT": ["T013"], "ク": ["T099"]}},
            night_assignments={}, requests={}, on_call_assignments={},
            daikyu_counts={}, off_counts={}, validation_errors=[],
            daily_location_needs={16: {"CT": 3}})

    monkeypatch.setattr(api_main, "RUNNER", fake_runner)
    resp = client.post(f"/rosters/{rid}/resolve", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] > ver
    assert "grid" in body and "warnings" in body and "unlockable" in body
    # locked cell preserved verbatim; unlocked cell replaced by the fake's output.
    assert tuple(_day_row(conn, rid, "T013")) == ("CT", 1)
    assert tuple(_day_row(conn, rid, "T099")) == ("ク", 0)
    # a synthetic op='resolve' edit was recorded.
    edits = conn.execute(
        "SELECT op FROM roster_edits WHERE roster_id=? ORDER BY seq", (rid,)).fetchall()
    assert edits[-1]["op"] == "resolve"


def test_resolve_returns_422_on_lock_conflict(client, seeded_roster, monkeypatch):
    rid = seeded_roster
    _lock_t013_ct(client, rid)

    def fake_runner(year, month, data_dir, *, locked_assignments=None, **kw):
        r = ScheduleResult(
            year=year, month=month, staff=[], day_assignments={16: {"CT": ["T013"]}},
            night_assignments={}, requests={}, on_call_assignments={},
            daikyu_counts={}, off_counts={}, validation_errors=[])
        r.lock_conflicts = [{"staff_id": "T013", "location": "CT",
                             "date": "2026-06-16", "mode": "force"}]
        return r

    monkeypatch.setattr(api_main, "RUNNER", fake_runner)
    resp = client.post(f"/rosters/{rid}/resolve", json={})
    assert resp.status_code == 422
    assert "conflicts" in resp.json()["detail"]


def test_resolve_pre_validate_422_before_solve(client, conn, seeded_roster, monkeypatch):
    """Two work locks for one staff/day is structurally impossible -> 422 with NO solve."""
    rid = seeded_roster
    _lock_t013_ct(client, rid)
    # add a second conflicting locked work cell for T013 on the same day.
    conn.execute(
        "INSERT OR IGNORE INTO roster_assignments(roster_id,staff_id,date,kind,"
        "location_or_role,locked) VALUES(?,?,?,'day',?,1)",
        (rid, "T013", "2026-06-16", "病CT"))
    conn.commit()
    called = {"n": 0}

    def fake_runner(*a, **kw):
        called["n"] += 1
        raise AssertionError("solver must NOT run on a structurally-impossible lock set")

    monkeypatch.setattr(api_main, "RUNNER", fake_runner)
    resp = client.post(f"/rosters/{rid}/resolve", json={})
    assert resp.status_code == 422
    assert called["n"] == 0
    assert resp.json()["detail"]["stage"] == "pre_validate"


def test_resolve_surfaces_unlockable(client, seeded_roster, monkeypatch):
    rid = seeded_roster
    _lock_t013_ct(client, rid)
    unlockable = [{"staff_id": "T013", "location": "CT",
                   "date": "2026-06-16", "reason": "no_var"}]

    def fake_runner(year, month, data_dir, *, locked_assignments=None, **kw):
        r = ScheduleResult(
            year=year, month=month,
            staff=[{"id": "T013", "name": "甲"}, {"id": "T099", "name": "乙"}],
            day_assignments={16: {"CT": ["T013"], "MG": ["T099"]}},
            night_assignments={}, requests={}, on_call_assignments={},
            daikyu_counts={}, off_counts={}, validation_errors=[])
        r.unlockable_locks = unlockable
        return r

    monkeypatch.setattr(api_main, "RUNNER", fake_runner)
    resp = client.post(f"/rosters/{rid}/resolve", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["unlockable"] == unlockable


def test_resolve_is_undoable(client, conn, seeded_roster, monkeypatch):
    rid = seeded_roster
    _lock_t013_ct(client, rid)

    def fake_runner(year, month, data_dir, *, locked_assignments=None, **kw):
        return ScheduleResult(
            year=year, month=month,
            staff=[{"id": "T013", "name": "甲"}, {"id": "T099", "name": "乙"}],
            day_assignments={16: {"CT": ["T013"], "ク": ["T099"]}},
            night_assignments={}, requests={}, on_call_assignments={},
            daikyu_counts={}, off_counts={}, validation_errors=[],
            daily_location_needs={16: {"CT": 3}})

    monkeypatch.setattr(api_main, "RUNNER", fake_runner)
    resolved = client.post(f"/rosters/{rid}/resolve", json={}).json()
    assert tuple(_day_row(conn, rid, "T099")) == ("ク", 0)
    # one undo restores the complete pre-resolve grid.
    u = client.post(f"/rosters/{rid}/undo", json={"expected_version": resolved["version"]})
    assert u.status_code == 200, u.text
    assert tuple(_day_row(conn, rid, "T099")) == ("MG", 0)
    assert tuple(_day_row(conn, rid, "T013")) == ("CT", 1)


# ===========================================================================
# Tasks 3-7,9 — real-solver lock injection / diagnostics (slow).
#
# Concrete (staff_id, loc, day) cells are DERIVED from the committed golden so
# each pick is guaranteed skill-eligible / currently-assigned by construction
# (the golden is byte-identical to run_schedule output, per test_parity_golden).
# ===========================================================================

with open(GOLDEN, encoding="utf-8") as _f:
    _G = json.load(_f)
_GDAY = _G["day_assignments"]      # {"16": {"CT": [...], "休": [...], ...}}
_GNIGHT = _G["night_assignments"]  # {"12": ["T013", ...]}
_GREQ = _G["requests"]             # {"16": {"T022": "DX", ...}}
_OFF = {"休", "○"}
_HOLIDAY_SYMS = {"★", "★連", "☆", "☆小", "☆デ", "◆", "退職", "☆育"}
# Protected/special staff whose cells are pinned by individual rules — avoid them
# so a force/off pick isn't fighting a hard individual constraint.
_AVOID = {"T001", "T002", "T013", "T022", "T025", "T072"}
# General high-headroom locations (always multi-staffed, many eligibles) — using
# these keeps a force/off feasible (no MRI/late single-eligible hard coverage).
_GENERAL = ("CT", "病CT", "ク")


def _staff_loc_on(day):
    out = {}
    for loc, ids in _GDAY.get(str(day), {}).items():
        for sid in ids:
            out[sid] = loc
    return out


def _pick_force_appear(exclude=()):
    """(D, S, L, A): S is OFF on day D with no request, eligible for a GENERAL
    work-loc L (assigned L on another day), L exists on D with an occupant A to
    forbid (keeps headcount balanced so a `<=need` cap can't break the force)."""
    for D in range(2, 28):
        sd = str(D)
        if D in exclude or sd not in _GDAY:
            continue
        off_staff = set(_GDAY[sd].get("休", []))
        reqs = _GREQ.get(sd, {})
        for S in sorted(off_staff):
            if S in reqs or S in _AVOID:
                continue
            for D2 in range(1, 31):
                if D2 == D:
                    continue
                L = _staff_loc_on(D2).get(S)
                if L in _GENERAL and L in _GDAY[sd]:
                    occ = [a for a in _GDAY[sd][L] if a != S and a not in _AVOID]
                    if occ:
                        return D, S, L, occ[0]
    return None


def _pick_off_lock(exclude=()):
    """(D, S, L): S works a GENERAL loc L (>=3 occupants) on day D, no request."""
    for D in range(2, 28):
        if D in exclude:
            continue
        for loc in _GENERAL:
            ids = _GDAY.get(str(D), {}).get(loc, [])
            if len(ids) < 3:
                continue
            for S in ids:
                if S not in _AVOID and S not in _GREQ.get(str(D), {}):
                    return D, S, loc
    return None


def _pick_pruned(exclude=()):
    """(D, S): S has a pure-holiday request symbol on day D -> no BoolVar that day."""
    for D in range(2, 28):
        if D in exclude:
            continue
        for S, sym in _GREQ.get(str(D), {}).items():
            if sym in _HOLIDAY_SYMS:
                return D, S
    return None


def _pick_forbid_late(exclude=()):
    """(D, S, L): S occupies a FROZEN late loc on day D (frozen in both post-
    processors, so a solve-level forbid survives to the final output)."""
    for D in range(2, 28):
        if D in exclude:
            continue
        for loc in ("超遅", "ク遅", "M遅"):
            ids = _GDAY.get(str(D), {}).get(loc, [])
            if ids:
                return D, ids[0], loc
    return None


def _pick_night(exclude=()):
    """(D, S): S is night-capable (appears in some golden night) and is free of
    nights on D-1/D/D+1 (no-consec safe) for D in mid-month."""
    union = set()
    for ids in _GNIGHT.values():
        union.update(ids)
    for D in range(6, 25):
        if D in exclude:
            continue
        around = (set(_GNIGHT.get(str(D - 1), [])) | set(_GNIGHT.get(str(D), []))
                  | set(_GNIGHT.get(str(D + 1), [])))
        reqs = _GREQ.get(str(D), {})
        for S in sorted(union):
            # no request on D (avoid holiday-blocked nights — the night model raises
            # on INFEASIBLE rather than degrading), and no-consec safe around D.
            if S not in around and S not in _AVOID and S not in reqs:
                return D, S
    return None


@pytest.mark.slow
def test_day_force_off_pruned_and_forbid_in_one_solve():
    """Tasks 3/4/6: a forced cell appears AND survives all post-processors; an
    OFF-locked staff stays off; a pruned-var force is reported (not swallowed); a
    solve-level forbid on a frozen late loc is excluded. All on distinct days in a
    single run (the forced cell is the post-processor survival proof)."""
    fa = _pick_force_appear(); assert fa, "no force-appear cell derivable from golden"
    Dfa = fa[0]
    ol = _pick_off_lock(exclude={Dfa}); assert ol, "no off-lock cell derivable"
    Dol = ol[0]
    pr = _pick_pruned(exclude={Dfa, Dol}); assert pr, "no pruned-staff cell derivable"
    Dpr = pr[0]
    fb = _pick_forbid_late(exclude={Dfa, Dol, Dpr}); assert fb, "no frozen-late forbid"
    (Dfa, Sfa, Lfa, Afa), (Dol, Sol, Lol), (Dpr, Spr), (Dfb, Sfb, Lfb) = fa, ol, pr, fb
    # keep the days distinct so the locks don't interact.
    assert len({Dfa, Dol, Dpr, Dfb}) == 4, (Dfa, Dol, Dpr, Dfb)

    def _mk(*entries):
        out = {}
        for d, force, forbid in entries:
            out[date(2026, 6, d)] = {"force": set(force), "forbid": set(forbid)}
        return out

    la = _mk(
        (Dfa, {(Sfa, Lfa)}, {(Afa, Lfa)}),     # force S into L, free a slot via forbid A
        (Dol, {(Sol, "休")}, set()),            # OFF-lock
        (Dpr, {(Spr, "CT")}, set()),            # pruned force -> unlockable
        (Dfb, set(), {(Sfb, Lfb)}),             # forbid on a frozen late loc
    )
    r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)

    # Task 3 + Task 6: forced cell present in the FINAL output (survived post-procs).
    assert Sfa in r.day_assignments.get(Dfa, {}).get(Lfa, []), (Dfa, Sfa, Lfa)
    # the force-appear day solved cleanly (no assumption conflict on that day).
    assert not any(c["date"] == f"2026-06-{Dfa:02d}" for c in r.lock_conflicts), r.lock_conflicts
    # OFF-lock: staff not in any work location that day.
    worked = any(Sol in ids for loc, ids in r.day_assignments.get(Dol, {}).items()
                 if loc not in _OFF)
    assert not worked, (Dol, Sol)
    # Task 4: pruned-var force surfaced, never silently dropped.
    assert any(u["staff_id"] == Spr and u["location"] == "CT"
               and u["date"] == f"2026-06-{Dpr:02d}" for u in r.unlockable_locks)
    # forbid on a frozen late loc holds end-to-end.
    assert Sfb not in r.day_assignments.get(Dfb, {}).get(Lfb, []), (Dfb, Sfb, Lfb)


@pytest.mark.slow
def test_conflicting_lock_reports_offending_cells():
    """Task 7: an impossible lock (work + OFF for one staff/day) returns the exact
    offending cells via SufficientAssumptionsForInfeasibility, not a silent degrade."""
    ol = _pick_off_lock(); assert ol
    D, S, L = ol
    la = {date(2026, 6, D): {"force": {(S, L), (S, "休")}, "forbid": set()}}
    r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
    cells = {(c["staff_id"], c["location"], c["date"]) for c in r.lock_conflicts}
    iso = f"2026-06-{D:02d}"
    assert (S, L, iso) in cells, (cells, S, L, iso)
    assert (S, "休", iso) in cells, (cells, S, iso)


@pytest.mark.slow
def test_night_force_occupancy_and_no_day_domain_leak():
    """Task 5: a '夜'-domain force adds night occupancy; a same-day day-domain force
    must NOT leak into the night model."""
    # a day-domain force on the SAME day: a staff working a GENERAL loc that day who
    # is NOT in the golden night set (so the night re-solve can't legitimately pull
    # them in — any night appearance would be a day-domain leak).
    # NB: _pick_night's FIRST candidate day may have a GENERAL roster that is entirely
    # night-capable (no leak-probe Sd), so iterate over candidate days until one yields
    # BOTH a night-force Sn and a leak-probe Sd (this golden has 14 such days).
    night_union = set().union(*[set(v) for v in _GNIGHT.values()]) if _GNIGHT else set()
    picked, excl = None, ()
    while True:
        nt = _pick_night(exclude=excl)
        if not nt:
            break
        D, Sn = nt
        day_map = _staff_loc_on(D)
        Sd = next((s for s, l in sorted(day_map.items())
                   if l in _GENERAL and s != Sn and s not in _AVOID and s not in night_union),
                  None)
        if Sd:
            picked = (D, Sn, Sd, day_map[Sd])
            break
        excl = excl + (D,)
    assert picked, "no (night-force day, day-domain leak-probe) pair derivable from golden"
    D, Sn, Sd, Ld = picked
    la = {date(2026, 6, D): {"force": {(Sn, "夜"), (Sd, Ld)}, "forbid": set()}}
    r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
    # '夜'-domain force adds night occupancy.
    assert Sn in r.night_assignments.get(D, []), (D, Sn, r.night_assignments.get(D))
    # day-domain force landed in the DAY model (reassert guarantees it) ...
    assert Sd in r.day_assignments.get(D, {}).get(Ld, []), (D, Sd, Ld)
    # ... and did NOT leak into the night model.
    assert Sd not in r.night_assignments.get(D, []), "day-domain lock leaked to nights"


@pytest.mark.slow
def test_resolve_real_solver_preserves_lock_and_is_deterministic(tmp_path):
    """Task 9: freeze a real 2026-06 roster, lock a real work cell, /resolve with the
    REAL solver; assert 200, lock preserved in the grid, version bumped, op='resolve'
    recorded; a second /resolve on the same lock returns an identical grid."""
    from shift_scheduler.src.loaders.data_loader import DataLoader

    result = run_schedule(2026, 6, data_dir=DATA_DIR)
    technicians = DataLoader(data_dir=DATA_DIR).load_all("2026-06")[0]
    c = connect(str(tmp_path / "real.db"))
    init_db(c)
    rid = freeze_roster(c, job_id="real", result=result, technicians=technicians,
                        data_dir=DATA_DIR, target_holidays=9)
    c.commit()

    # lock a real work cell from the frozen grid.
    ol = _pick_off_lock(); assert ol
    D, S, L = ol
    iso = f"2026-06-{D:02d}"
    # ensure the (S, L) day row exists in the freeze, then lock it.
    row = c.execute("SELECT 1 FROM roster_assignments WHERE roster_id=? AND staff_id=? "
                    "AND date=? AND kind='day' AND location_or_role=?",
                    (rid, S, iso, L)).fetchone()
    assert row is not None, (S, L, iso)
    c.execute("UPDATE roster_assignments SET locked=1 WHERE roster_id=? AND staff_id=? "
              "AND date=? AND kind='day' AND location_or_role=?", (rid, S, iso, L))
    c.commit()

    app.dependency_overrides[api_main.get_db] = lambda: c
    monkey_prev = api_main.RUNNER
    api_main.RUNNER = run_schedule  # the REAL solver
    try:
        client = TestClient(app)
        resp = client.post(f"/rosters/{rid}/resolve", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version"] > 0
        locked_row = c.execute(
            "SELECT location_or_role,locked FROM roster_assignments WHERE roster_id=? "
            "AND staff_id=? AND date=? AND kind='day' AND locked=1", (rid, S, iso)).fetchone()
        assert tuple(locked_row) == (L, 1)
        edits = c.execute("SELECT op FROM roster_edits WHERE roster_id=? ORDER BY seq",
                          (rid,)).fetchall()
        assert any(e["op"] == "resolve" for e in edits)
        grid1 = body["grid"]
        # second resolve on the same lock set -> identical grid (determinism).
        resp2 = client.post(f"/rosters/{rid}/resolve", json={})
        assert resp2.status_code == 200, resp2.text
        assert _canon(resp2.json()["grid"]) == _canon(grid1)
    finally:
        app.dependency_overrides.clear()
        api_main.RUNNER = monkey_prev
        c.close()
