from shift_scheduler.src.models.schedule_result import ScheduleResult


def _sample():
    return ScheduleResult(
        year=2026, month=6,
        staff=[{"id": "T002", "name": "B"}, {"id": "T001", "name": "A"}],
        day_assignments={2: {"CT": ["T002", "T001"]}},
        night_assignments={3: ["T002", "T001"]},
        requests={1: {"T001": "☆"}},
        on_call_assignments={5: {"第1拘束": "T001"}},
        daikyu_counts={"T001": 0},
        off_counts={"T001": 9},
        validation_errors=["x"],
        workbook_bytes=b"PK\x03\x04",
    )


def test_as_dict_excludes_bytes_and_is_deterministic():
    d = _sample().as_dict()
    assert "workbook_bytes" not in d
    # staff-id lists are sorted so ordering never causes false parity mismatches
    assert d["day_assignments"]["2"]["CT"] == ["T001", "T002"]
    assert d["night_assignments"]["3"] == ["T001", "T002"]
    # integer day keys are stringified for stable JSON round-tripping
    assert set(d["requests"].keys()) == {"1"}
    assert d["year"] == 2026 and d["month"] == 6
