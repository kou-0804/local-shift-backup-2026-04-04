"""Per-master CRUD: pure ``(conn, master_set_id, ...)`` functions that validate
first, then mutate the typed tables. Edits should target a clone (see
``clone_master_set``) so the seeded "現行" set stays pristine.
"""
from datetime import datetime

from . import validation as v
from . import safety

# Tables deep-copied by clone (all carry master_set_id). Order is irrelevant.
CLONE_TABLES = [
    "ms_staff", "ms_skill_row", "ms_skill_cell", "ms_location", "ms_power_balance",
    "ms_special_rule", "ms_training", "ms_night_quota", "ms_night_override",
    "ms_holiday_target", "master_file_profile",
]


def _rows(conn, sql, params):
    return [dict(r) for r in conn.execute(sql, params)]


def _next_row_order(conn, table, msid):
    r = conn.execute(
        f"SELECT COALESCE(MAX(row_order)+1, 0) n FROM {table} WHERE master_set_id=?",
        (msid,)).fetchone()
    return r[0] if not hasattr(r, "keys") else r["n"]


# --- staff ----------------------------------------------------------------

def list_staff(conn, msid):
    return _rows(conn, "SELECT * FROM ms_staff WHERE master_set_id=? ORDER BY row_order",
                 (msid,))


def create_staff(conn, msid, payload: dict):
    existing = {r["tech_id"] for r in conn.execute(
        "SELECT tech_id FROM ms_staff WHERE master_set_id=?", (msid,))}
    v.validate_staff_row(payload, existing_ids=existing)
    ro = _next_row_order(conn, "ms_staff", msid)
    conn.execute(
        "INSERT INTO ms_staff(master_set_id,row_order,tech_id,name,gender,"
        "experience_years,night_ok,status,note,oncall_ok)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (msid, ro, payload["tech_id"], payload.get("name", ""), payload.get("gender"),
         int(payload.get("experience_years", 0)), payload.get("night_ok"),
         payload.get("status"), payload.get("note", ""), payload.get("oncall_ok")))
    conn.commit()
    return {"tech_id": payload["tech_id"], "row_order": ro}


def update_staff(conn, msid, tech_id, payload: dict):
    cur = dict(conn.execute(
        "SELECT * FROM ms_staff WHERE master_set_id=? AND tech_id=?",
        (msid, tech_id)).fetchone() or {})
    if not cur:
        raise KeyError(tech_id)
    merged = {**cur, **payload, "tech_id": tech_id}
    v.validate_staff_row(merged)  # tech_id unchanged -> no uniqueness check
    conn.execute(
        "UPDATE ms_staff SET name=?,gender=?,experience_years=?,night_ok=?,"
        "status=?,note=?,oncall_ok=? WHERE master_set_id=? AND tech_id=?",
        (merged.get("name"), merged.get("gender"), int(merged.get("experience_years", 0)),
         merged.get("night_ok"), merged.get("status"), merged.get("note", ""),
         merged.get("oncall_ok"), msid, tech_id))
    conn.commit()
    return {"tech_id": tech_id}


def delete_staff(conn, msid, tech_id):
    conn.execute("DELETE FROM ms_staff WHERE master_set_id=? AND tech_id=?", (msid, tech_id))
    conn.commit()
    return {"deleted": tech_id}


# --- skill -----------------------------------------------------------------

def list_skill(conn, msid):
    rows = []
    for sr in conn.execute(
        "SELECT * FROM ms_skill_row WHERE master_set_id=? ORDER BY row_order", (msid,)):
        cells = {c["loc_code"]: c["rank"] for c in conn.execute(
            "SELECT loc_code,rank FROM ms_skill_cell WHERE master_set_id=? AND tech_id=?",
            (msid, sr["tech_id"]))}
        rows.append({"tech_id": sr["tech_id"], "name": sr["name"], "cells": cells})
    return rows


def update_skill(conn, msid, tech_id, cells: dict):
    for loc, rank in cells.items():
        v.validate_skill_rank(rank)
    warnings = []
    for loc, rank in cells.items():
        old = conn.execute(
            "SELECT rank FROM ms_skill_cell WHERE master_set_id=? AND tech_id=? AND loc_code=?",
            (msid, tech_id, loc)).fetchone()
        old_rank = old["rank"] if old else "-"
        warnings += safety.night_eligibility_warnings(
            conn, msid, tech_id=tech_id, loc_code=loc, old_rank=old_rank, new_rank=rank)
        conn.execute(
            "UPDATE ms_skill_cell SET rank=? WHERE master_set_id=? AND tech_id=? AND loc_code=?",
            (rank, msid, tech_id, loc))
    conn.commit()
    return {"tech_id": tech_id, "updated": list(cells.keys()), "warnings": warnings}


# --- holiday_targets -------------------------------------------------------

def list_holiday_targets(conn, msid):
    return _rows(conn,
                 "SELECT * FROM ms_holiday_target WHERE master_set_id=? ORDER BY row_order",
                 (msid,))


def upsert_holiday_target(conn, msid, year_month, holiday_count):
    v.validate_year_month(year_month)
    existing = conn.execute(
        "SELECT id FROM ms_holiday_target WHERE master_set_id=? AND year_month=?",
        (msid, year_month)).fetchone()
    if existing:
        conn.execute("UPDATE ms_holiday_target SET holiday_count=? WHERE id=?",
                     (int(holiday_count), existing["id"]))
    else:
        ro = _next_row_order(conn, "ms_holiday_target", msid)
        conn.execute(
            "INSERT INTO ms_holiday_target(master_set_id,row_order,year_month,holiday_count)"
            " VALUES(?,?,?,?)", (msid, ro, year_month, int(holiday_count)))
    conn.commit()
    return {"year_month": year_month, "holiday_count": int(holiday_count)}


def delete_holiday_target(conn, msid, year_month):
    # Route keys arrive hyphenated (2027-03); stored form is slashed (2027/03).
    ym = year_month.replace("-", "/")
    conn.execute("DELETE FROM ms_holiday_target WHERE master_set_id=? AND year_month=?",
                 (msid, ym))
    conn.commit()
    return {"deleted": ym}


# --- generic list (read-only) for the remaining masters --------------------

_LIST_TABLES = {
    "location": "ms_location",
    "power_balance": "ms_power_balance",
    "special_rules": "ms_special_rule",
    "training": "ms_training",
    "night_quota": "ms_night_quota",
    "night_overrides": "ms_night_override",
}


def list_generic(conn, msid, master):
    table = _LIST_TABLES[master]
    return _rows(conn, f"SELECT * FROM {table} WHERE master_set_id=? ORDER BY row_order",
                 (msid,))


# --- master-set listing ----------------------------------------------------

def list_master_sets(conn):
    return [{"master_set_id": r["id"], "name": r["name"],
             "created_at": r["created_at"], "parent_set_id": r["parent_set_id"]}
            for r in conn.execute(
                "SELECT id,name,created_at,parent_set_id FROM master_set ORDER BY id")]


# --- write endpoints (P3a-2): replace-all per master -----------------------
# Each rebuilds row_order from list position so materialize (ORDER BY row_order)
# reproduces CSV line order. Validation runs BEFORE any mutation -> a 422 leaves
# the set untouched. Edits should target a clone (clone_master_set).

def replace_location_set(conn, msid, locations, power_balance):
    """ATOMIC 2-table replace (勤務場所マスタ is one CSV with sections A+B)."""
    loc_codes = set()
    for r in locations:
        v.validate_location_row(r)
        loc_codes.add(r.get("loc_code"))
    for r in power_balance:
        v.validate_pb_location_ref(r.get("loc_code"), loc_codes)
    try:
        conn.execute("DELETE FROM ms_location WHERE master_set_id=?", (msid,))
        conn.execute("DELETE FROM ms_power_balance WHERE master_set_id=?", (msid,))
        for i, r in enumerate(locations):
            conn.execute(
                "INSERT INTO ms_location(master_set_id,row_order,loc_code,loc_name,"
                "category,mon,tue,wed,thu,fri,sat,sun,gender_constraint,display_order,"
                "active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (msid, i, r.get("loc_code"), r.get("loc_name"), r.get("category"),
                 r.get("mon"), r.get("tue"), r.get("wed"), r.get("thu"), r.get("fri"),
                 r.get("sat"), r.get("sun"), r.get("gender_constraint"),
                 r.get("display_order"), r.get("active")))
        for i, r in enumerate(power_balance):
            conn.execute(
                "INSERT INTO ms_power_balance(master_set_id,row_order,loc_code,min_rank,"
                "min_count,cd_cap,d_solo_ban) VALUES(?,?,?,?,?,?,?)",
                (msid, i, r.get("loc_code"), r.get("min_rank"), r.get("min_count"),
                 r.get("cd_cap"), r.get("d_solo_ban")))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"locations": len(locations), "power_balance": len(power_balance)}


def replace_special_rules(conn, msid, rows):
    warnings = []
    for r in rows:
        v.validate_rule_id(r.get("rule_id"))
        v.validate_special_rule_row(r)
        warnings += safety.special_rule_warnings(r.get("rank_cond"))
    conn.execute("DELETE FROM ms_special_rule WHERE master_set_id=?", (msid,))
    for i, r in enumerate(rows):
        conn.execute(
            "INSERT INTO ms_special_rule(master_set_id,row_order,rule_id,loc_code,"
            "weekday,week,required_count,rank_cond,rank_count,source_loc,source_rank,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (msid, i, r.get("rule_id"), r.get("loc_code"), r.get("weekday"),
             r.get("week"), r.get("required_count"), r.get("rank_cond"),
             r.get("rank_count"), r.get("source_loc"), r.get("source_rank"),
             r.get("note")))
    conn.commit()
    return {"count": len(rows), "warnings": warnings}


def _split_names(text):
    return [n.strip() for n in (text or "").replace("，", ",").split(",") if n.strip()]


def _resolve_ids(names, name_to_id):
    """Substring match mirroring import_dir (full/half-width space tolerant)."""
    out = []
    for n in names:
        clean = n.replace(" ", "").replace("　", "")
        for nm, tid in name_to_id.items():
            nmc = nm.replace("　", "").replace(" ", "")
            if clean and (clean in nmc or nmc in clean):
                out.append(tid)
                break
    return out


def replace_training(conn, msid, rows):
    name_to_id = {r["name"]: r["tech_id"] for r in conn.execute(
        "SELECT name,tech_id FROM ms_staff WHERE master_set_id=?", (msid,))}
    staff_names = set(name_to_id)
    # Collect every name that must resolve (instructor names skipped when the row
    # uses the ランクA保持者 sentinel). Validate once -> 422 lists all unresolved.
    to_check = []
    for r in rows:
        instr = r.get("instructor_text") or ""
        if "ランクA保持者" not in instr:
            to_check += _split_names(instr)
        to_check += _split_names(r.get("trainee_text"))
    import json as _json
    v.validate_training_names(to_check, staff_names)
    conn.execute("DELETE FROM ms_training WHERE master_set_id=?", (msid,))
    for i, r in enumerate(rows):
        instr = r.get("instructor_text") or ""
        rank_a_only = "ランクA保持者" in instr
        instr_ids = [] if rank_a_only else _resolve_ids(_split_names(instr), name_to_id)
        trainee_ids = _resolve_ids(_split_names(r.get("trainee_text")), name_to_id)
        conn.execute(
            "INSERT INTO ms_training(master_set_id,row_order,modality,instructor_text,"
            "trainee_text,display_name,instructor_ids_json,trainee_ids_json,rank_a_only)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (msid, i, r.get("modality"), instr, r.get("trainee_text"),
             r.get("display_name"), _json.dumps(instr_ids), _json.dumps(trainee_ids),
             int(rank_a_only)))
    conn.commit()
    return {"count": len(rows)}


def replace_night_quota(conn, msid, year_month, rows):
    for r in rows:
        v.validate_quota_count(r.get("count"))
    conn.execute("DELETE FROM ms_night_quota WHERE master_set_id=?", (msid,))
    for i, r in enumerate(rows):
        conn.execute(
            "INSERT INTO ms_night_quota(master_set_id,row_order,year_month,tech_id,name,"
            "count) VALUES(?,?,?,?,?,?)",
            (msid, i, year_month, r.get("tech_id"), r.get("name"), int(r.get("count"))))
    conn.commit()
    return {"count": len(rows), "year_month": year_month}


def replace_night_overrides(conn, msid, rows):
    for r in rows:
        for fld in ("night_mr", "night_cath", "night_angio"):
            v.validate_night_override_state(r.get(fld), fld)
    conn.execute("DELETE FROM ms_night_override WHERE master_set_id=?", (msid,))
    for i, r in enumerate(rows):
        conn.execute(
            "INSERT INTO ms_night_override(master_set_id,row_order,sname,tech_id,"
            "night_mr,night_cath,night_angio,qual_code) VALUES(?,?,?,?,?,?,?,?)",
            (msid, i, r.get("sname"), r.get("tech_id"), r.get("night_mr"),
             r.get("night_cath"), r.get("night_angio"), r.get("qual_code")))
    conn.commit()
    return {"count": len(rows)}


# --- clone -----------------------------------------------------------------

def clone_master_set(conn, src_id, created_by="", name=None):
    """Deep-copy a master_set (rows + file profiles) into a new child set.

    The copy is faithful enough that a no-op clone materializes byte-identical to
    the source (verified in tests), so edits can target the clone while the seed
    stays pristine."""
    src = conn.execute("SELECT * FROM master_set WHERE id=?", (src_id,)).fetchone()
    if src is None:
        raise KeyError(src_id)
    created_at = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO master_set(name,note,created_at,created_by,parent_set_id)"
        " VALUES(?,?,?,?,?)",
        (name or f"{src['name']}のコピー", src["note"], created_at, created_by, src_id))
    new_id = cur.lastrowid
    for t in CLONE_TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] != "id"]
        collist = ",".join(cols)
        placeholders = ",".join("?" * len(cols))
        msid_idx = cols.index("master_set_id")
        for row in conn.execute(
                f"SELECT {collist} FROM {t} WHERE master_set_id=? ORDER BY id", (src_id,)):
            vals = list(row)
            vals[msid_idx] = new_id
            conn.execute(f"INSERT INTO {t}({collist}) VALUES({placeholders})", vals)
    conn.commit()
    return new_id
