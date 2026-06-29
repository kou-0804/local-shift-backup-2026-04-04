"""Render a ``master_set`` back into byte-identical CSVs (the keystone).

Each logical master is reconstructed into the exact ``list[list[str]]`` that
``csv.reader`` produced at import time (verified byte-identical by the round-trip
golden gate), then serialized via ``profiles.write_bytes`` and written in BINARY
mode so Windows never re-translates newlines.
"""
import json
import os

from .import_dir import MASTER_FILES
from .profiles import FileProfile, write_bytes


def _load_profile(conn, msid, logical_name) -> FileProfile:
    r = conn.execute(
        "SELECT * FROM master_file_profile WHERE master_set_id=? AND logical_name=?",
        (msid, logical_name)).fetchone()
    if r is None:
        raise KeyError(f"no file profile for {logical_name} in master_set {msid}")
    return FileProfile(
        logical_name=r["logical_name"], filename=r["filename"],
        has_bom=bool(r["has_bom"]), newline=r["newline"],
        trailing_newline=bool(r["trailing_newline"]), header_text=r["header_text"],
        format_json=json.loads(r["format_json"]) if r["format_json"] else {})


def _rows_staff(conn, msid, fj):
    rows = [fj["header"]]
    for r in conn.execute(
        "SELECT * FROM ms_staff WHERE master_set_id=? ORDER BY row_order", (msid,)):
        rows.append([r["tech_id"], r["name"], r["gender"], str(r["experience_years"]),
                     r["night_ok"], r["status"], r["note"], r["oncall_ok"]])
    return rows


def _rows_skill(conn, msid, fj):
    columns = fj["columns"]
    rows = [fj["header"]]
    for sr in conn.execute(
        "SELECT * FROM ms_skill_row WHERE master_set_id=? ORDER BY row_order", (msid,)):
        cells = {c["loc_code"]: c["rank"] for c in conn.execute(
            "SELECT loc_code,rank FROM ms_skill_cell WHERE master_set_id=? AND tech_id=?",
            (msid, sr["tech_id"]))}
        rows.append([sr["tech_id"], sr["name"]] + [cells[c] for c in columns])
    return rows


def _rows_holiday(conn, msid, fj):
    rows = [fj["header"]]
    for r in conn.execute(
        "SELECT * FROM ms_holiday_target WHERE master_set_id=? ORDER BY row_order", (msid,)):
        rows.append([r["year_month"], str(r["holiday_count"])])
    return rows


def _rows_location_pb(conn, msid, fj):
    rows = [fj["header"]]
    for r in conn.execute(
        "SELECT * FROM ms_location WHERE master_set_id=? ORDER BY row_order", (msid,)):
        rows.append([r["loc_code"], r["loc_name"], r["category"], r["mon"], r["tue"],
                     r["wed"], r["thu"], r["fri"], r["sat"], r["sun"],
                     r["gender_constraint"], r["display_order"], r["active"]])
    rows.append(fj["separator_row"])
    rows.append(fj["pad_row"])
    rows.append(fj["sectionb_header"])
    width = fj["field_width"]
    for r in conn.execute(
        "SELECT * FROM ms_power_balance WHERE master_set_id=? ORDER BY row_order", (msid,)):
        base = [r["loc_code"], r["min_rank"], r["min_count"], r["cd_cap"], r["d_solo_ban"]]
        rows.append(base + [""] * (width - len(base)))
    return rows


def _rows_special_rules(conn, msid, fj):
    rows = [fj["header"]]
    for r in conn.execute(
        "SELECT * FROM ms_special_rule WHERE master_set_id=? ORDER BY row_order", (msid,)):
        rows.append([r["rule_id"], r["loc_code"], r["weekday"], r["week"],
                     r["required_count"], r["rank_cond"], r["rank_count"],
                     r["source_loc"], r["source_rank"], r["note"]])
    rows.extend(fj["tail_rows"])
    return rows


def _rows_training(conn, msid, fj):
    rows = [fj["header"]]
    for r in conn.execute(
        "SELECT * FROM ms_training WHERE master_set_id=? ORDER BY row_order", (msid,)):
        rows.append([r["modality"], r["instructor_text"], r["trainee_text"],
                     r["display_name"]])
    return rows


def _rows_night_quota(conn, msid, fj):
    rows = [fj["title_row"], fj["header_row"]]
    total = 0
    for r in conn.execute(
        "SELECT * FROM ms_night_quota WHERE master_set_id=? ORDER BY row_order", (msid,)):
        total += int(r["count"])
        rows.append([r["name"], str(r["count"]), ""])
    rows.append(["合計", str(total), ""])
    req = fj.get("footer_required_row")
    if req is not None:
        rows.append(req)
    return rows


def _rows_night_override(conn, msid, fj):
    width = fj["data_width"]
    rows = [fj["header_row"]]
    for r in conn.execute(
        "SELECT * FROM ms_night_override WHERE master_set_id=? ORDER BY row_order", (msid,)):
        base = [r["sname"], r["night_mr"], r["night_cath"], r["night_angio"], r["qual_code"]]
        rows.append(base + [""] * (width - len(base)))
    return rows


_RENDERERS = {
    "staff": _rows_staff,
    "skill": _rows_skill,
    "holiday_targets": _rows_holiday,
    "location_pb": _rows_location_pb,
    "special_rules": _rows_special_rules,
    "training": _rows_training,
    "night_quota": _rows_night_quota,
    "night_override": _rows_night_override,
}


def materialize_masters(conn, master_set_id: int, *, dest_dir: str) -> None:
    """Write all 8 master CSVs into ``dest_dir`` byte-identical to the source set."""
    for logical_name, _ in MASTER_FILES:
        profile = _load_profile(conn, master_set_id, logical_name)
        rows = _RENDERERS[logical_name](conn, master_set_id, profile.format_json)
        data = write_bytes(rows, profile)
        # Binary write + newline pre-embedded: the OS never re-translates \n.
        with open(os.path.join(dest_dir, profile.filename), "wb") as f:
            f.write(data)


def materialize_data_dir(conn, master_set_id: int, year: int, month: int,
                         request_import_id, dest_dir: str) -> None:
    """Full job data dir: 8 masters + the selected 予定申請 import (month-suffixed).

    The 予定申請 blob is written verbatim from ``requests_import.raw_blob`` to
    ``予定申請_{year}{month:02d}.csv`` so ``request_loader`` picks it over any
    generic fallback (no stale-month bug).
    """
    materialize_masters(conn, master_set_id, dest_dir=dest_dir)
    if request_import_id is not None:
        row = conn.execute(
            "SELECT raw_blob FROM requests_import WHERE id=?", (request_import_id,)).fetchone()
        if row is not None and row["raw_blob"] is not None:
            fname = f"予定申請_{year}{month:02d}.csv"
            with open(os.path.join(dest_dir, fname), "wb") as f:
                f.write(bytes(row["raw_blob"]))
