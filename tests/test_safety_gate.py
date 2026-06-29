# tests/test_safety_gate.py
import sqlite3

import pytest

from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.safety import (
    LOAD_BEARING_IDS, assert_load_bearing_ids, SafetyError,
    night_eligibility_warnings, special_rule_warnings)

DATA = "shift_scheduler/data"


def _mem():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_master_db(c)
    return c


def test_load_bearing_ids_constant_is_exact():
    assert LOAD_BEARING_IDS == ["T001", "T013", "T025", "T072", "T002", "T022", "T006", "T023"]


def test_gate_passes_on_intact_master_set():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    assert_load_bearing_ids(c, msid)  # must not raise


def test_gate_fails_with_specific_id_when_missing():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    c.execute("DELETE FROM ms_staff WHERE master_set_id=? AND tech_id='T072'", (msid,))
    with pytest.raises(SafetyError) as e:
        assert_load_bearing_ids(c, msid)
    assert "T072" in str(e.value)


def test_night_eligibility_warning_on_skill_downgrade():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    warns = night_eligibility_warnings(c, msid, tech_id="T001", loc_code="病院MR",
                                       old_rank="A", new_rank="C")
    assert warns and "夜勤" in warns[0]


def test_no_warning_when_below_threshold_both_sides():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    warns = night_eligibility_warnings(c, msid, tech_id="T001", loc_code="病院MR",
                                       old_rank="C", new_rank="D")
    assert warns == []


def test_special_rule_warning_on_unenforced_string_condition():
    warns = special_rule_warnings(rank_cond="D同士禁止")
    assert warns and ("未適用" in warns[0] or "未実装" in warns[0])
