"""予定申請 (Power Apps) import — import-only (NOT CRUD).

Upload -> validate (BOM tolerant, skip Sample Data / blank rows) -> preview
(report unresolved RSName) -> store per-month. The raw bytes are kept verbatim
in ``requests_import.raw_blob`` so ``materialize_data_dir`` can write a
byte-exact ``予定申請_YYYYMM.csv`` (a raw BLOB is correct here, not a shortcut:
this file is never edited cell-by-cell — it is replaced by re-upload).

HolidaySymbol legend (for the UI): 公休(◆ 等) / 出勤強制 / 夜希(夜勤希望) / 17休・17業.
"""
import csv
import io
import re
from datetime import datetime

BOM = b"\xef\xbb\xbf"

HOLIDAY_SYMBOL_LEGEND = {
    "◆": "公休希望",
    "夜希": "夜勤希望",
    "☆デ": "デイ希望/出勤系",
    "17休": "17時退勤(休)",
    "17業": "17時退勤(業務)",
}


def _decode(raw: bytes):
    has_bom = raw.startswith(BOM)
    body = raw[len(BOM):] if has_bom else raw
    text = body.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing_newline = body.endswith(b"\n")
    return text, has_bom, newline, trailing_newline


def _find_header(rows):
    """HolidaySymbol/日付 header within the first 5 physical lines."""
    for i, r in enumerate(rows[:5]):
        if any(c in ("HolidaySymbol", "日付") for c in r):
            return i
    return 0


def _resolve(rs_name: str, name_to_id: dict):
    rs = (rs_name or "").strip()
    name_part = re.sub(r"^[\d]+\s*", "", rs)
    if name_part in name_to_id:
        return name_to_id[name_part], "resolved"
    # ID fallback (matches request_loader): "03" -> "T003"
    parts = re.split(r"\s+", rs)
    raw_id = parts[0] if parts else rs
    if raw_id.isdigit():
        return f"T{int(raw_id):03d}", "id_fallback"
    return (raw_id or None), "unresolved"


def preview_requests(raw: bytes, name_to_id: dict) -> dict:
    """Parse + classify rows without persisting. Returns row_count, rows, unresolved."""
    text, *_ = _decode(raw)
    all_rows = list(csv.reader(io.StringIO(text)))
    h = _find_header(all_rows)
    header = all_rows[h]
    idx = {name: i for i, name in enumerate(header)}
    out_rows, unresolved = [], []
    for r in all_rows[h + 1:]:
        if not r or all(c.strip() == "" for c in r):
            continue
        def cell(col):
            return r[idx[col]] if col in idx and idx[col] < len(r) else ""
        symbol = cell("HolidaySymbol")
        ppp = cell("PPPDate")
        rsname = cell("RSName")
        if not symbol.strip() or not ppp.strip() or not rsname.strip():
            continue
        if "Sample Data" in rsname:
            continue
        try:
            d = datetime.strptime(ppp.strip(), "%Y/%m/%d").date().isoformat()
        except ValueError:
            d = ppp.strip()
        tech_id, status = _resolve(rsname, name_to_id)
        row = {"date": d, "symbol": symbol, "raw_rsname": rsname,
               "tech_id_resolved": tech_id, "resolve_status": status}
        out_rows.append(row)
        if status != "resolved":
            unresolved.append(row)
    return {"row_count": len(out_rows), "rows": out_rows, "unresolved": unresolved,
            "legend": HOLIDAY_SYMBOL_LEGEND}


def store_requests(conn, year: int, month: int, raw: bytes, source_filename: str,
                   imported_by: str, name_to_id: dict) -> int:
    """Persist raw bytes verbatim + parsed request_row rows. Returns import_id."""
    _, has_bom, newline, trailing_newline = _decode(raw)
    pv = preview_requests(raw, name_to_id)
    imported_at = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO requests_import(year_month,source_filename,imported_at,imported_by,"
        "raw_blob,has_bom,newline,trailing_newline) VALUES(?,?,?,?,?,?,?,?)",
        (f"{year}-{month:02d}", source_filename, imported_at, imported_by,
         sqlite3_blob(raw), int(has_bom), newline, int(trailing_newline)))
    imp_id = cur.lastrowid
    for row in pv["rows"]:
        conn.execute(
            "INSERT INTO request_row(import_id,tech_id_resolved,date,symbol,raw_rsname,"
            "resolve_status) VALUES(?,?,?,?,?,?)",
            (imp_id, row["tech_id_resolved"], row["date"], row["symbol"],
             row["raw_rsname"], row["resolve_status"]))
    conn.commit()
    return imp_id


def sqlite3_blob(raw: bytes):
    """Store bytes verbatim (sqlite3 BLOB)."""
    return memoryview(raw)
