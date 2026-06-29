"""Parse the current ``shift_scheduler/data/`` CSVs into a ``master_set``.

This is the *starting point* bundle. We parse with stdlib ``csv`` (never pandas),
preserve CSV row order (``row_order``), store the semantically meaningful rows in
typed tables for CRUD, and capture each file's byte profile + structural
scaffolding (separators / legends / footers / column order / pad widths) into
``master_file_profile.format_json`` so the serializer can rebuild exact bytes.
"""
import csv
import io
import json
import os
from datetime import datetime
from typing import List

from .profiles import BOM, capture_profile

# logical_name -> filename. Order is the canonical iteration order.
MASTER_FILES = [
    ("staff", "技師マスタ_確定版.csv"),
    ("skill", "スキルマスタ_確定版.csv"),
    ("holiday_targets", "公休数マスタ_確定版.csv"),
    ("location_pb", "勤務場所マスタ_確定版.csv"),
    ("special_rules", "特殊配置ルール_確定版.csv"),
    ("training", "業務拡大マスタ_確定版.csv"),
    ("night_quota", "夜勤回数_確定版.csv"),
    ("night_override", "夜勤スキル一覧.csv"),
]
REQUESTS_FILE = ("requests", "予定申請.csv")

SEPARATOR_TOKEN = "---パワーバランス設定---"


def _read_rows(path: str) -> List[List[str]]:
    """Decode (BOM-tolerant) and parse into list[list[str]] via stdlib csv."""
    raw = open(path, "rb").read()
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    return list(csv.reader(io.StringIO(raw.decode("utf-8"))))


def _save_profile(conn, msid, path, logical_name, format_json):
    p = capture_profile(path, logical_name=logical_name, format_json=format_json)
    conn.execute(
        "INSERT INTO master_file_profile(master_set_id,logical_name,filename,"
        "has_bom,newline,trailing_newline,header_text,format_json)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (msid, p.logical_name, p.filename, int(p.has_bom), p.newline,
         int(p.trailing_newline), p.header_text, json.dumps(p.format_json, ensure_ascii=False)))


def _name_keys(name: str):
    """Yield the name plus space-variant so full/half-width spaces both join."""
    yield name
    if "　" in name:
        yield name.replace("　", " ")
    if " " in name:
        yield name.replace(" ", "　")


def import_dir(conn, data_dir: str, name: str = "現行", created_by: str = "") -> int:
    """Import all 8 master CSVs (+ capture 予定申請 profile) into a new master_set."""
    created_at = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO master_set(name,note,created_at,created_by,parent_set_id)"
        " VALUES(?,?,?,?,NULL)", (name, "imported from data/", created_at, created_by))
    msid = cur.lastrowid

    _import_staff(conn, msid, os.path.join(data_dir, "技師マスタ_確定版.csv"))
    name_to_id = {r["name"]: r["tech_id"] for r in conn.execute(
        "SELECT name,tech_id FROM ms_staff WHERE master_set_id=?", (msid,))}

    _import_skill(conn, msid, os.path.join(data_dir, "スキルマスタ_確定版.csv"))
    _import_holiday(conn, msid, os.path.join(data_dir, "公休数マスタ_確定版.csv"))
    _import_location_pb(conn, msid, os.path.join(data_dir, "勤務場所マスタ_確定版.csv"))
    _import_special_rules(conn, msid, os.path.join(data_dir, "特殊配置ルール_確定版.csv"))
    _import_training(conn, msid, os.path.join(data_dir, "業務拡大マスタ_確定版.csv"), name_to_id)
    _import_night_quota(conn, msid, os.path.join(data_dir, "夜勤回数_確定版.csv"), name_to_id)
    _import_night_override(conn, msid, os.path.join(data_dir, "夜勤スキル一覧.csv"), name_to_id)

    # 9th profile: capture 予定申請 byte truth (rows live in requests_import, not here).
    req_path = os.path.join(data_dir, "予定申請.csv")
    if os.path.exists(req_path):
        _save_profile(conn, msid, req_path, "requests", {})

    conn.commit()
    return msid


def _resolve(name_to_id, raw_name):
    name = (raw_name or "").strip()
    for k in _name_keys(name):
        if k in name_to_id:
            return name_to_id[k]
    return None


def _import_staff(conn, msid, path):
    rows = _read_rows(path)
    header, data = rows[0], rows[1:]
    for i, r in enumerate(data):
        conn.execute(
            "INSERT INTO ms_staff(master_set_id,row_order,tech_id,name,gender,"
            "experience_years,night_ok,status,note,oncall_ok)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (msid, i, r[0], r[1], r[2], int(r[3]), r[4], r[5], r[6], r[7]))
    _save_profile(conn, msid, path, "staff", {"header": header})


def _import_skill(conn, msid, path):
    rows = _read_rows(path)
    header, data = rows[0], rows[1:]
    columns = header[2:]  # location codes after 技師ID,氏名
    for i, r in enumerate(data):
        tech_id, sname = r[0], r[1]
        conn.execute(
            "INSERT INTO ms_skill_row(master_set_id,row_order,tech_id,name)"
            " VALUES(?,?,?,?)", (msid, i, tech_id, sname))
        for j, code in enumerate(columns):
            conn.execute(
                "INSERT INTO ms_skill_cell(master_set_id,tech_id,loc_code,rank)"
                " VALUES(?,?,?,?)", (msid, tech_id, code, r[2 + j]))
    _save_profile(conn, msid, path, "skill", {"header": header, "columns": columns})


def _import_holiday(conn, msid, path):
    rows = _read_rows(path)
    header, data = rows[0], rows[1:]
    for i, r in enumerate(data):
        conn.execute(
            "INSERT INTO ms_holiday_target(master_set_id,row_order,year_month,holiday_count)"
            " VALUES(?,?,?,?)", (msid, i, r[0], int(r[1])))
    _save_profile(conn, msid, path, "holiday_targets", {"header": header})


def _import_location_pb(conn, msid, path):
    rows = _read_rows(path)
    sep = next(i for i, r in enumerate(rows) if r and r[0] == SEPARATOR_TOKEN)
    header = rows[0]
    loc_rows = rows[1:sep]
    separator_row, pad_row, sectionb_header = rows[sep], rows[sep + 1], rows[sep + 2]
    pb_rows = rows[sep + 3:]
    for i, r in enumerate(loc_rows):
        conn.execute(
            "INSERT INTO ms_location(master_set_id,row_order,loc_code,loc_name,category,"
            "mon,tue,wed,thu,fri,sat,sun,gender_constraint,display_order,active)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (msid, i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9],
             r[10], r[11], r[12]))
    field_width = len(separator_row)
    for i, r in enumerate(pb_rows):
        conn.execute(
            "INSERT INTO ms_power_balance(master_set_id,row_order,loc_code,min_rank,"
            "min_count,cd_cap,d_solo_ban) VALUES(?,?,?,?,?,?,?)",
            (msid, i, r[0], r[1], r[2], r[3], r[4]))
    _save_profile(conn, msid, path, "location_pb", {
        "header": header, "separator_row": separator_row, "pad_row": pad_row,
        "sectionb_header": sectionb_header, "field_width": field_width})


def _import_special_rules(conn, msid, path):
    rows = _read_rows(path)
    header = rows[0]
    sr_rows, tail_rows, in_tail = [], [], False
    for r in rows[1:]:
        if not in_tail and r and str(r[0]).startswith("SR-"):
            sr_rows.append(r)
        else:
            in_tail = True
            tail_rows.append(r)
    for i, r in enumerate(sr_rows):
        conn.execute(
            "INSERT INTO ms_special_rule(master_set_id,row_order,rule_id,loc_code,"
            "weekday,week,required_count,rank_cond,rank_count,source_loc,source_rank,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (msid, i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
    _save_profile(conn, msid, path, "special_rules",
                  {"header": header, "tail_rows": tail_rows})


def _import_training(conn, msid, path, name_to_id):
    rows = _read_rows(path)
    header, data = rows[0], rows[1:]

    def resolve_list(text):
        out = []
        for n in (text or "").replace("，", ",").split(","):
            n = n.strip()
            if not n:
                continue
            clean = n.replace(" ", "").replace("　", "")
            mid = None
            for nm, tid in name_to_id.items():
                if clean and (clean in nm.replace("　", "").replace(" ", "")
                              or nm.replace("　", "").replace(" ", "") in clean):
                    mid = tid
                    break
            if mid:
                out.append(mid)
        return out

    for i, r in enumerate(data):
        modality, instr_text, trainee_text, display = r[0], r[1], r[2], r[3]
        rank_a_only = "ランクA保持者" in instr_text
        instr_ids = [] if rank_a_only else resolve_list(instr_text)
        trainee_ids = resolve_list(trainee_text)
        conn.execute(
            "INSERT INTO ms_training(master_set_id,row_order,modality,instructor_text,"
            "trainee_text,display_name,instructor_ids_json,trainee_ids_json,rank_a_only)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (msid, i, modality, instr_text, trainee_text, display,
             json.dumps(instr_ids), json.dumps(trainee_ids), int(rank_a_only)))
    _save_profile(conn, msid, path, "training", {"header": header})


def _import_night_quota(conn, msid, path, name_to_id):
    rows = _read_rows(path)
    title_row, header_row = rows[0], rows[1]
    body = rows[2:]
    # footer rows = 合計 / 必要当直者数 (last two); the rest are per-staff.
    footer_required = None
    staff_rows = []
    for r in body:
        if r and r[0] == "合計":
            continue
        if r and r[0] == "必要当直者数":
            footer_required = r
            continue
        staff_rows.append(r)
    month_header = header_row[1] if len(header_row) > 1 else ""
    for i, r in enumerate(staff_rows):
        nm, cnt = r[0], r[1]
        conn.execute(
            "INSERT INTO ms_night_quota(master_set_id,row_order,year_month,tech_id,name,count)"
            " VALUES(?,?,?,?,?,?)",
            (msid, i, month_header, _resolve(name_to_id, nm), nm, int(cnt)))
    _save_profile(conn, msid, path, "night_quota", {
        "title_row": title_row, "header_row": header_row,
        "month_header": month_header, "footer_required_row": footer_required})


def _import_night_override(conn, msid, path, name_to_id):
    rows = _read_rows(path)
    header_row, data = rows[0], rows[1:]
    data_width = len(header_row)
    for i, r in enumerate(data):
        sname = r[0]
        conn.execute(
            "INSERT INTO ms_night_override(master_set_id,row_order,sname,tech_id,"
            "night_mr,night_cath,night_angio,qual_code) VALUES(?,?,?,?,?,?,?,?)",
            (msid, i, sname, _resolve(name_to_id, sname), r[1], r[2], r[3], r[4]))
    _save_profile(conn, msid, path, "night_override",
                  {"header_row": header_row, "data_width": data_width})
