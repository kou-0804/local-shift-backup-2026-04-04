# tests/test_requests_import.py
import sqlite3

from webapp.api.masters.schema import init_master_db
from webapp.api.requests_import import (
    preview_requests,
    store_requests,
    _normalize_to_comma_csv,
)

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


def test_reimport_same_month_overwrites_previous():
    """2026-07 policy: re-importing the same month REPLACES the prior import (no
    accumulation). Exactly one requests_import row remains — the newest — and the
    old import's request_row children are gone."""
    c = _mem()
    n2i = {"矢野　昌男": "T003"}
    raw1 = "HolidaySymbol,PPPDate,RSName\r\n◆,2026/08/01,03 矢野　昌男\r\n".encode("utf-8")
    raw2 = ("HolidaySymbol,PPPDate,RSName\r\n☆,2026/08/05,03 矢野　昌男\r\n"
            "◆,2026/08/06,03 矢野　昌男\r\n").encode("utf-8")
    id1 = store_requests(c, year=2026, month=8, raw=raw1,
                         source_filename="a.csv", imported_by="t", name_to_id=n2i)
    id2 = store_requests(c, year=2026, month=8, raw=raw2,
                         source_filename="b.csv", imported_by="t", name_to_id=n2i)
    rows = c.execute("SELECT id, source_filename FROM requests_import "
                     "WHERE year_month='2026-08'").fetchall()
    assert len(rows) == 1                     # overwrite, not accumulate
    assert rows[0]["source_filename"] == "b.csv"   # newest content kept
    kept_id = rows[0]["id"]
    assert c.execute("SELECT COUNT(*) n FROM request_row WHERE import_id=?",
                     (kept_id,)).fetchone()["n"] == 2     # exactly raw2's 2 rows
    # no orphan children left pointing at a now-deleted import (sqlite rowid may be
    # reused when the table empties, so assert across all imports rather than by id).
    assert c.execute("SELECT COUNT(*) n FROM request_row WHERE import_id NOT IN "
                     "(SELECT id FROM requests_import)").fetchone()["n"] == 0


def test_preview_accepts_tab_separated_paste():
    """Power Apps copies the table as TSV; preview must parse it like the comma CSV."""
    tsv = (
        "HolidaySymbol\tPPPDate\tRSName\r\n"
        "◆\t2026/07/01\t03 矢野　昌男\r\n"
        "☆\t2026/07/04\t14 下田　あず沙\r\n"
        "\t2026/07/07\t99 Sample Data \r\n"  # blank symbol → skipped
    ).encode("utf-8")
    pv = preview_requests(tsv, {"矢野　昌男": "T003"})
    assert pv["row_count"] == 2
    assert pv["skipped"] >= 1
    assert {r["symbol"] for r in pv["rows"]} == {"◆", "☆"}
    resolved = [r for r in pv["rows"] if r["resolve_status"] == "resolved"]
    assert any(r["tech_id_resolved"] == "T003" for r in resolved)


def test_normalize_tab_paste_to_canonical_comma_csv():
    """A TAB paste becomes canonical comma CSV (BOM, no tabs) — what RequestLoader reads."""
    tsv = (
        "HolidaySymbol\tPPPDate\tRSName\r\n"
        "◆\t2026/07/01\t03 矢野　昌男\r\n"
    ).encode("utf-8")
    norm = _normalize_to_comma_csv(tsv)
    assert norm.startswith(b"\xef\xbb\xbf")        # BOM
    assert b"\t" not in norm                        # tabs converted
    assert b"HolidaySymbol,PPPDate,RSName" in norm
    assert not norm.endswith(b"\r\n")               # no trailing newline (canonical)


def test_normalize_leaves_comma_csv_unchanged():
    """Comma input (uploaded file) passes through byte-for-byte (verbatim re-upload)."""
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    assert _normalize_to_comma_csv(raw) == raw


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
