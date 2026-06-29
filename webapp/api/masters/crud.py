"""Per-master CRUD: pure ``(conn, master_set_id, ...)`` functions that validate
first, then mutate the typed tables. Edits should target a clone (see
``clone_master_set``) so the seeded "現行" set stays pristine.
"""
from datetime import datetime

from . import validation as v

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
    for loc, rank in cells.items():
        conn.execute(
            "UPDATE ms_skill_cell SET rank=? WHERE master_set_id=? AND tech_id=? AND loc_code=?",
            (rank, msid, tech_id, loc))
    conn.commit()
    return {"tech_id": tech_id, "updated": list(cells.keys())}


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
