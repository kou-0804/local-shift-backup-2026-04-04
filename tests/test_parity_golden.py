# tests/test_parity_golden.py
import json
import os
import pytest

from main import run_schedule

DATA_DIR = "shift_scheduler/data"
GOLDEN = "tests/golden/2026-06_assignments.json"


@pytest.mark.slow
def test_run_schedule_matches_golden_snapshot():
    assert os.path.exists(GOLDEN), "golden snapshot missing — generate it (see plan Task 4 Step 4)"
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    actual = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    # round-trip through json so int/str key handling matches the stored file
    actual = json.loads(json.dumps(actual, ensure_ascii=False, sort_keys=True))
    expected = json.loads(json.dumps(expected, ensure_ascii=False, sort_keys=True))
    assert actual == expected


@pytest.mark.slow
def test_run_schedule_is_deterministic_across_two_runs():
    a = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    b = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    assert a == b
