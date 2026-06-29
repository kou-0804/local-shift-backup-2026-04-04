# tests/test_master_validation.py
import pytest

from webapp.api.masters import validation as v


def test_tech_id_must_be_tnnn():
    with pytest.raises(v.ValidationError):
        v.validate_staff_row({"tech_id": "X1", "name": "a　b", "gender": "男",
                              "experience_years": 3, "night_ok": "○",
                              "status": "在籍", "oncall_ok": "○"})


def test_valid_staff_row_passes():
    v.validate_staff_row({"tech_id": "T999", "name": "試験　太郎", "gender": "男",
                          "experience_years": 3, "night_ok": "○",
                          "status": "在籍", "oncall_ok": "×"})


def test_tech_id_unique_within_set():
    with pytest.raises(v.ValidationError):
        v.validate_tech_id_unique(existing={"T001"}, tech_id="T001")


def test_skill_rank_domain():
    for r in ["A", "B", "C", "D", "-"]:
        v.validate_skill_rank(r)
    with pytest.raises(v.ValidationError):
        v.validate_skill_rank("E")


def test_holiday_year_month_must_be_zero_padded():
    v.validate_year_month("2026/04")
    with pytest.raises(v.ValidationError):
        v.validate_year_month("2026/4")   # the #1 silent footgun


def test_full_width_space_name_join_integrity():
    with pytest.raises(v.ValidationError):
        v.validate_name_join("石川 和弥", known_names={"石川　和弥"})


def test_power_balance_code_must_reference_location():
    with pytest.raises(v.ValidationError):
        v.validate_pb_location_ref("存在しない", location_codes={"病院MR", "CT"})


def test_night_quota_total_must_equal_sum():
    with pytest.raises(v.ValidationError):
        v.validate_night_quota_total(rows_sum=92, declared_total=93)


def test_training_names_must_resolve():
    with pytest.raises(v.ValidationError):
        v.validate_training_names(["幽霊"], staff_names={"小川　龍史"})


def test_special_rule_weekday_and_week_domains():
    v.validate_special_rule_row({"weekday": "水金", "week": "-", "required_count": "2"})
    with pytest.raises(v.ValidationError):
        v.validate_special_rule_row({"weekday": "金曜", "week": "-", "required_count": "1"})
