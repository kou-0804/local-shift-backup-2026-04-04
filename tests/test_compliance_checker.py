"""Fast, solver-free tests for compliance_checker: plant known violations and
assert the checker reports them. Uses duck-typed fakes so no full solve runs."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shift_scheduler.src.models.skill import SkillRank
from shift_scheduler.src import compliance_checker as cc


class FakeLoc:
    def __init__(self, code, req=1, gender_constraint=None, is_active=True):
        self.code = code
        self.name = code
        self.gender_constraint = gender_constraint
        self.is_active = is_active
        self._req = req

    def get_required_count(self, weekday):
        return self._req


def staff(sid, name, gender='男', night_mr=False, night_angio=False,
          night_cath=False, status='在籍'):
    return SimpleNamespace(id=sid, name=name, gender=gender, status=status,
                           experience_years=5, night_mr=night_mr,
                           night_angio=night_angio, night_cath=night_cath,
                           night_hb=False, note='')


YEAR, MONTH, TARGET = 2026, 7, 9
# July 2026: day5=Sun -> day7=Tue, day1=Wed.


def _codes(violations):
    return {v['code'] for v in violations}


def base_setup():
    techs = [
        staff('M1', '男MG', gender='男'),
        staff('F1', '女MG', gender='女'),
        staff('N1', '夜1', night_mr=True),
        staff('N2', '夜2', night_mr=True),
        staff('N3', '夜3', night_mr=True),   # all MR-only -> NH-06 fails
        staff('C1', 'C技', gender='男'),
        staff('C2', 'C技2', gender='男'),
    ]
    skills = {
        'M1': {'MG': SkillRank.A, 'CT': SkillRank.C},
        'F1': {'MG': SkillRank.A},
        'C1': {'CT': SkillRank.C, 'ア': SkillRank.B, '精': SkillRank.C},
        'C2': {'CT': SkillRank.C, 'ア': SkillRank.B},
    }
    locations = [
        FakeLoc('MG', req=1, gender_constraint='female'),
        FakeLoc('CT', req=1),
        FakeLoc('ア', req=2),
        FakeLoc('精', req=1),
    ]
    pb_rules = [SimpleNamespace(location_code='CT', min_rank=SkillRank.A,
                               min_count=1, cd_cap=None, d_solo_ban=False)]
    return techs, skills, locations, pb_rules


def run(day_assignments, night_assignments):
    techs, skills, locations, pb_rules = base_setup()
    return cc.check_compliance(
        year=YEAR, month=MONTH, technicians=techs, skills=skills,
        locations=locations, pb_rules=pb_rules,
        day_assignments=day_assignments, night_assignments=night_assignments,
        requests={}, daily_location_needs=None, target_holidays=TARGET)


def test_gender_violation_detected():
    v = run({1: {'MG': ['M1']}}, {})       # male in female-only MG
    assert 'DH-06' in _codes(v)


def test_gender_ok_female():
    v = run({1: {'MG': ['F1']}}, {})       # female in MG -> no gender violation
    assert 'DH-06' not in _codes(v)


def test_ake_dayshift_detected():
    # N1 night on day1, then day-worked CT on day2 -> DH-05
    v = run({2: {'CT': ['N1']}}, {1: ['N1', 'N2', 'N3']})
    assert 'DH-05' in _codes(v)


def test_double_placement_detected():
    v = run({3: {'CT': ['C1'], 'ア': ['C1', 'C2']}}, {})
    assert 'DH-01' in _codes(v)


def test_pb_rank_floor_detected():
    # CT needs A>=1 but only C-rank assigned
    v = run({8: {'CT': ['C1']}}, {})
    assert 'PB-01' in _codes(v)


def test_sr01_angio_tuesday_detected():
    # day7 = Tuesday; ア with B-rank only -> A<2
    v = run({7: {'ア': ['C1', 'C2']}}, {})
    assert 'SR-01' in _codes(v)


def test_night_modality_matching_detected():
    # 3 night staff all MR-only -> no distinct MR/angio/cath cover
    v = run({}, {4: ['N1', 'N2', 'N3']})
    assert 'NH-06' in _codes(v)


def test_night_modality_ok():
    techs = [
        staff('A', 'mr', night_mr=True),
        staff('B', 'an', night_angio=True),
        staff('C', 'ca', night_cath=True),
    ]
    v = cc.check_compliance(
        year=YEAR, month=MONTH, technicians=techs, skills={}, locations=[],
        pb_rules=[], day_assignments={}, night_assignments={4: ['A', 'B', 'C']},
        requests={}, target_holidays=TARGET)
    assert 'NH-06' not in _codes(v)


def test_clean_schedule_has_no_real_violations():
    techs = [staff('A', 'mr', night_mr=True), staff('B', 'an', night_angio=True),
             staff('C', 'ca', night_cath=True)]
    v = cc.check_compliance(
        year=YEAR, month=MONTH, technicians=techs, skills={}, locations=[],
        pb_rules=[], day_assignments={}, night_assignments={1: ['A', 'B', 'C']},
        requests={}, target_holidays=TARGET)
    real = [x for x in v if x['severity'] != 'info']
    assert real == [], f"unexpected violations: {real}"


if __name__ == '__main__':
    fns = [g for n, g in sorted(globals().items()) if n.startswith('test_')]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok: {fn.__name__}")
    print(f"\n{passed}/{len(fns)} compliance_checker tests passed")
