import json
from types import SimpleNamespace

from shift_scheduler.src.stats_engine import recompute_stats

P2A1 = json.load(open("tests/golden/2026-06_p2a1.json", encoding="utf-8"))
DAY = {int(d): v for d, v in P2A1["day_assignments"].items()}
NIGHT = {int(d): v for d, v in P2A1["night_assignments"].items()}
REQ = {int(d): v for d, v in P2A1["requests"].items()}


def _techs(ids):
    return [SimpleNamespace(id=i, name=i, status="在籍", note="", night_hb=False)
            for i in ids]


def test_off_daikyu_idempotent_on_unedited_golden():
    techs = _techs(P2A1["active_staff_ids"])
    out = recompute_stats(DAY, NIGHT, REQ, techs, P2A1["year"], P2A1["month"],
                          P2A1["target_holidays"])
    assert out["off_counts"] == P2A1["expected_off_counts"]
    assert {k: v for k, v in out["daikyu_counts"].items() if v} == \
           {k: v for k, v in P2A1["expected_daikyu_counts"].items() if v}


def test_holiday_deficit_mirrors_daikyu():
    techs = _techs(["T001", "T002"])
    # T001 fully assigned weekdays (no off) -> deficit; T002 unassigned -> off via blanks
    day = {d: {"CT": ["T001"]} for d in range(1, 31)}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, target_holidays=9)
    deficits = {w["staff_id"]: w["short"] for w in out["holiday_deficit"]}
    assert "T001" in deficits and deficits["T001"] > 0
    assert "T002" not in deficits  # T002 accrues off from blank weekdays


def test_coverage_understaffing_and_kuL_fold():
    techs = _techs(["T001", "T002"])
    day = {1: {"クL": ["T001"]}}            # クL must count toward ク
    needs = {"2026-06-01": {"ク": 2, "(補助)": 5}}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, target_holidays=9,
                          daily_location_needs=needs)
    cov = out["coverage"]
    assert len(cov) == 1
    assert cov[0]["location"] == "ク" and cov[0]["required"] == 2
    assert cov[0]["assigned"] == 1 and cov[0]["short"] == 1   # クL folded in
    # parenthesized (補助) is skipped entirely
    assert all(c["location"] != "(補助)" for c in cov)


def test_night_hb_gap_detected():
    techs = [SimpleNamespace(id="T001", name="a", status="在籍", note="", night_hb=False),
             SimpleNamespace(id="T002", name="b", status="在籍", note="", night_hb=True)]
    night_gap = {1: ["T001"]}        # no HB-capable -> gap
    night_ok = {2: ["T002"]}         # HB-capable present -> no gap
    out_gap = recompute_stats({}, night_gap, {}, techs, 2026, 6, 9)
    out_ok = recompute_stats({}, night_ok, {}, techs, 2026, 6, 9)
    assert 1 in out_gap["night_hb_gaps"]
    assert out_ok["night_hb_gaps"] == []


def test_consecutive_run_of_seven_flagged():
    techs = _techs(["T001"])
    day = {d: {"CT": ["T001"]} for d in range(1, 8)}   # 7 straight work days
    out = recompute_stats(day, {}, {}, techs, 2026, 6, 9)
    cons = out["consecutive"]
    assert any(c["staff_id"] == "T001" and c["len"] >= 7 for c in cons)


def test_staff_scope_limits_per_staff_outputs():
    techs = _techs(["T001", "T002"])
    day = {1: {"CT": ["T001", "T002"]}}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, 9, staff_scope={"T001"})
    assert set(out["off_counts"]) == {"T001"}
