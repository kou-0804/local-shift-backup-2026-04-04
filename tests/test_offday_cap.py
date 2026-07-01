"""Verify the 2026-07 policy: surplus idle weekdays are left BLANK (not 休), so
公休 is capped at the target instead of inflating. Exercises stats_engine's
recompute_off_daikyu, which mirrors main.py assign_monthly_off_days' blanks_quota.

July 2026: Sundays/holidays = {5,12,19,20,26} (5 days) -> 26 non-off days.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shift_scheduler.src import stats_engine as se

YEAR, MONTH, TARGET = 2026, 7, 9
NON_OFF = [d for d in range(1, 32) if d not in (5, 12, 19, 20, 26)]  # 26 weekdays


def off(day_assignments, sid='X'):
    oc, dk = se.recompute_off_daikyu(
        day_assignments, night_assignments={}, requests={},
        staff_ids=[sid], year=YEAR, month=MONTH, target_holidays=TARGET)
    return oc[sid], dk[sid]


def test_fully_unscheduled_caps_at_target():
    # No work, no 休, no requests: 5 Sundays + 26 blank weekdays.
    # Old behavior counted all -> 31; new caps at 9.
    o, d = off({})
    assert o == 9, f"expected 9, got {o}"
    assert d == 0


def test_surplus_with_some_kyuu_markers_caps_at_target():
    # 4 '休' markers + a couple work days + many blanks -> still 9.
    da = {1: {'休': ['X']}, 2: {'休': ['X']}, 3: {'休': ['X']}, 4: {'休': ['X']},
          6: {'CT': ['X']}, 7: {'CT': ['X']}}
    o, d = off(da)
    assert o == 9, f"expected 9, got {o}"
    assert d == 0


def test_genuinely_understaffed_still_gets_daikyu():
    # Works EVERY weekday (26), only Sundays off -> off=5, 代休=4.
    da = {day: {'CT': ['X']} for day in NON_OFF}
    o, d = off(da)
    assert o == 5, f"expected 5, got {o}"
    assert d == 4, f"expected daikyu 4, got {d}"


def test_exactly_target_no_surplus_unchanged():
    # 5 Sundays + exactly 4 '休' + rest work -> off=9, no surplus, no daikyu.
    kyuu = NON_OFF[:4]
    work = NON_OFF[4:]
    da = {day: {'休': ['X']} for day in kyuu}
    da.update({day: {'CT': ['X']} for day in work})
    o, d = off(da)
    assert o == 9, f"expected 9, got {o}"
    assert d == 0


def test_half_day_counts_half_above_explicit():
    # 出/☆ half day contributes 0.5 on top of the capped baseline.
    # 5 Sundays + 4 休 (=9 explicit) + one 出/☆ half -> 9 + 0.5 = 9.5.
    da = {day: {'休': ['X']} for day in NON_OFF[:4]}
    da.update({day: {'CT': ['X']} for day in NON_OFF[5:]})
    reqs = {NON_OFF[4]: {'X': '出/☆'}}
    oc, dk = se.recompute_off_daikyu(
        da, night_assignments={}, requests=reqs, staff_ids=['X'],
        year=YEAR, month=MONTH, target_holidays=TARGET)
    assert oc['X'] == 9.5, f"expected 9.5, got {oc['X']}"


if __name__ == '__main__':
    fns = [g for n, g in sorted(globals().items()) if n.startswith('test_')]
    for fn in fns:
        fn()
        print(f"  ok: {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} off-day cap tests passed")
