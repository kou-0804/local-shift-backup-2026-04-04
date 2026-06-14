from dataclasses import dataclass

from main import _in_rotation


@dataclass
class _S:
    id: str
    note: str = ""
    experience_years: int = 10


def test_separate_department_excluded():
    assert _in_rotation(_S("T058", note="核医学"), rest_val=31, num_days=31) is False
    assert _in_rotation(_S("T067", note="治療"), rest_val=31, num_days=31) is False


def test_mri_specialist_excluded():
    assert _in_rotation(_S("T005", note="MRI専門"), rest_val=9.5, num_days=31) is False


def test_new_staff_excluded():
    assert _in_rotation(_S("T057", note="", experience_years=1), rest_val=31, num_days=31) is False


def test_long_leave_excluded():
    # 大島/原田: 当月ほぼ全休（育休/長期休）
    assert _in_rotation(_S("T026", note="", experience_years=5), rest_val=21, num_days=31) is False
    assert _in_rotation(_S("T021", note="", experience_years=9), rest_val=31, num_days=31) is False


def test_normal_rotation_member_included():
    # 須田(+2)・河西(+1)・森(+0.5) は対象
    assert _in_rotation(_S("T011", note="", experience_years=18), rest_val=11, num_days=31) is True
    assert _in_rotation(_S("T007", note="", experience_years=25), rest_val=10, num_days=31) is True
    assert _in_rotation(_S("T024", note="", experience_years=7), rest_val=9.5, num_days=31) is True


def test_deficit_member_included():
    # 代休者(公休<目標)は当然ローテ内
    assert _in_rotation(_S("T036", note="", experience_years=4), rest_val=8.5, num_days=31) is True


from main import _coexistence_report


def test_coexistence_report_counts():
    # rest_map: id -> 公休相当. target=9
    rest_map = {"A": 8.5, "B": 8.5, "C": 11, "D": 10, "E": 9}
    rep = _coexistence_report(rest_map, target=9)
    assert rep["n_under"] == 2
    assert rep["n_over"] == 2
    assert rep["daikyu_days"] == 1.0          # (9-8.5)*2
    assert rep["surplus_days"] == 3.0         # (11-9)+(10-9)
    assert rep["coexists"] is True


def test_coexistence_report_no_deficit():
    rest_map = {"A": 9, "B": 10, "C": 11}
    rep = _coexistence_report(rest_map, target=9)
    assert rep["n_under"] == 0
    assert rep["coexists"] is False
