import json
from shift_scheduler.src.stats_engine import recompute_off_daikyu

with open("tests/golden/2026-06_p2a1.json", encoding="utf-8") as f:
    FIX = json.load(f)

DAY = {int(d): v for d, v in FIX["day_assignments"].items()}
NIGHT = {int(d): v for d, v in FIX["night_assignments"].items()}
REQ = {int(d): v for d, v in FIX["requests"].items()}


def test_recompute_off_daikyu_matches_golden():
    off, daikyu = recompute_off_daikyu(
        day_assignments=DAY, night_assignments=NIGHT, requests=REQ,
        staff_ids=FIX["active_staff_ids"], year=FIX["year"], month=FIX["month"],
        target_holidays=FIX["target_holidays"],
    )
    # daikyu is only stored when > 0 downstream (.get(sid,0)); compare on that basis
    assert off == FIX["expected_off_counts"]
    assert {k: v for k, v in daikyu.items() if v} == \
           {k: v for k, v in FIX["expected_daikyu_counts"].items() if v}
