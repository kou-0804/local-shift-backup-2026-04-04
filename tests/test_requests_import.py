# tests/test_requests_import.py
import sqlite3

from webapp.api.masters.schema import init_master_db
from webapp.api.requests_import import preview_requests, store_requests

DATA = "shift_scheduler/data"


def _mem():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_master_db(c)
    return c


def test_preview_skips_sample_and_blank_rows():
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    name_to_id = {"矢野　昌男": "T003"}  # minimal; real test uses imported staff
    pv = preview_requests(raw, name_to_id)
    assert pv["row_count"] > 0
    assert all("Sample Data" not in r["raw_rsname"] for r in pv["rows"])


def test_preview_reports_unresolved_rsname():
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    pv = preview_requests(raw, name_to_id={})       # nothing resolves by name
    assert pv["unresolved"]                          # surfaced, not silently dropped


def test_preview_resolves_known_name():
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    pv = preview_requests(raw, {"矢野　昌男": "T003"})
    resolved = [r for r in pv["rows"] if r["resolve_status"] == "resolved"]
    assert resolved and resolved[0]["tech_id_resolved"] == "T003"


def test_store_keeps_raw_bytes_for_byte_exact_materialize():
    c = _mem()
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    imp_id = store_requests(c, year=2026, month=6, raw=raw,
                            source_filename="予定申請.csv", imported_by="t", name_to_id={})
    stored = c.execute(
        "SELECT raw_blob FROM requests_import WHERE id=?", (imp_id,)).fetchone()["raw_blob"]
    assert bytes(stored) == raw                      # verbatim -> 予定申請_202606.csv byte-exact


def test_store_writes_request_rows_and_year_month():
    c = _mem()
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    imp_id = store_requests(c, year=2026, month=6, raw=raw,
                            source_filename="予定申請.csv", imported_by="t",
                            name_to_id={"矢野　昌男": "T003"})
    n = c.execute("SELECT COUNT(*) n FROM request_row WHERE import_id=?", (imp_id,)).fetchone()["n"]
    assert n > 0
    ym = c.execute("SELECT year_month FROM requests_import WHERE id=?", (imp_id,)).fetchone()["year_month"]
    assert ym == "2026-06"
