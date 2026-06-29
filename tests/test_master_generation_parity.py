# tests/test_master_generation_parity.py
import json
import os
import shutil
import sqlite3
import tempfile

import pytest

from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.materialize import materialize_masters
from main import run_schedule

DATA = "shift_scheduler/data"
GOLDEN = "tests/golden/2026-06_assignments.json"


def _mem():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_master_db(c)
    return c


@pytest.mark.slow
def test_run_schedule_via_materialized_dir_matches_golden():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(c, msid, dest_dir=tmp)
        # request file: copy the current 予定申請.csv in as the month-suffixed name
        shutil.copyfile(os.path.join(DATA, "予定申請.csv"),
                        os.path.join(tmp, "予定申請_202606.csv"))
        actual = run_schedule(2026, 6, data_dir=tmp).as_dict()
    expected = json.load(open(GOLDEN, encoding="utf-8"))
    actual = json.loads(json.dumps(actual, ensure_ascii=False, sort_keys=True))
    expected = json.loads(json.dumps(expected, ensure_ascii=False, sort_keys=True))
    assert actual == expected
