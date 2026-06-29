# tests/test_master_import.py
import sqlite3

from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir

DATA = "shift_scheduler/data"


def _mem():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_master_db(c)
    return c


def test_import_dir_creates_master_set_and_rows():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="kohei")
    assert msid == 1
    n_staff = c.execute(
        "SELECT COUNT(*) n FROM ms_staff WHERE master_set_id=?", (msid,)
    ).fetchone()["n"]
    assert n_staff == 72  # 72 data rows (67 在籍 + 5 退職)
    ids = {r["tech_id"] for r in c.execute(
        "SELECT tech_id FROM ms_staff WHERE master_set_id=?", (msid,))}
    assert {"T001", "T013", "T025", "T072", "T002", "T022", "T006", "T023"} <= ids
    profs = c.execute(
        "SELECT COUNT(*) n FROM master_file_profile WHERE master_set_id=?", (msid,)
    ).fetchone()["n"]
    assert profs == 9


def test_import_dir_preserves_row_order():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="kohei")
    first = c.execute(
        "SELECT tech_id FROM ms_staff WHERE master_set_id=? ORDER BY row_order LIMIT 1",
        (msid,)).fetchone()["tech_id"]
    assert first == "T001"  # CSV order is row order, not numeric-id order


def test_import_dir_section_b_additive_rows():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="kohei")
    n = c.execute(
        "SELECT COUNT(*) n FROM ms_power_balance WHERE master_set_id=? AND loc_code='病院MR'",
        (msid,)).fetchone()["n"]
    assert n == 2  # 病院MR appears twice (rank A min1, rank B min2)


def test_import_dir_skill_cells_and_training_flag():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="kohei")
    # skill long-form: T001 病CT rank C
    rank = c.execute(
        "SELECT rank FROM ms_skill_cell WHERE master_set_id=? AND tech_id='T001' AND loc_code='病CT'",
        (msid,)).fetchone()["rank"]
    assert rank == "C"
    # training rank_a_only flag set for ランクA保持者 rows
    flags = {r["rank_a_only"] for r in c.execute(
        "SELECT rank_a_only FROM ms_training WHERE master_set_id=?", (msid,))}
    assert flags == {1}
