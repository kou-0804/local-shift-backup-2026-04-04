import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from shift_scheduler.src.grid_derivation import build_grid
from shift_scheduler.src.stats_engine import recompute_stats


def _now():
    return datetime.now(timezone.utc).isoformat()


def _iso(year, month, day):
    return date(year, month, day).isoformat()


def _day_of(iso):
    return int(iso.split('-')[2])


def freeze_roster(conn, *, job_id, result, technicians, data_dir,
                  target_holidays, created_by=None) -> int:
    """Map a ScheduleResult -> rows (synthesis §2.1). Idempotent per job_id."""
    if job_id is not None:
        existing = conn.execute(
            "SELECT id FROM rosters WHERE job_id=?", (job_id,)).fetchone()
        if existing:
            return existing["id"]

    staff = [{"id": t.id, "name": t.name, "status": getattr(t, "status", "在籍"),
              "note": getattr(t, "note", "") or "",
              "night_hb": bool(getattr(t, "night_hb", False))}
             for t in technicians]
    needs = {_iso(result.year, result.month,
                  int(d) if not isinstance(d, date) else d.day):
             {lc: req for lc, req in locs.items()}
             for d, locs in (getattr(result, "daily_location_needs", {}) or {}).items()}

    cur = conn.execute(
        "INSERT INTO rosters(job_id,year,month,target_holidays,data_dir,staff_json,"
        "daily_needs_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (job_id, result.year, result.month, target_holidays, data_dir,
         json.dumps(staff, ensure_ascii=False),
         json.dumps(needs, ensure_ascii=False), created_by, _now()))
    rid = cur.lastrowid

    rows = []
    for d, locs in result.day_assignments.items():
        for loc, ids in locs.items():
            for sid in ids:
                rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                             "day", loc, None, 0))
    for d, ids in result.night_assignments.items():
        for sid in ids:
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "night", "夜", None, 0))
    for d, sm in result.requests.items():
        for sid, sym in sm.items():
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "request", None, sym, 0))
    for d, roles in (result.on_call_assignments or {}).items():
        for role, sid in roles.items():
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "oncall", role, None, 0))
    conn.executemany(
        "INSERT OR IGNORE INTO roster_assignments"
        "(roster_id,staff_id,date,kind,location_or_role,symbol,locked)"
        " VALUES(?,?,?,?,?,?,?)", rows)

    # roster_meta from build_grid stats (carries off/daikyu-injected 公休/代休).
    grid = build_grid(result.year, result.month, technicians,
                      {int(d): v for d, v in result.day_assignments.items()},
                      {int(d): v for d, v in result.night_assignments.items()},
                      {int(d): v for d, v in result.requests.items()},
                      off_counts=result.off_counts, daikyu_counts=result.daikyu_counts)
    for r in grid["rows"]:
        sid = r["staff_id"]
        conn.execute(
            "INSERT OR REPLACE INTO roster_meta(roster_id,staff_id,off_count,"
            "daikyu_count,stats_json) VALUES(?,?,?,?,?)",
            (rid, sid, float(result.off_counts.get(sid, 0)),
             float(result.daikyu_counts.get(sid, 0)),
             json.dumps(r["stats"] or {}, ensure_ascii=False)))
    conn.commit()
    return rid


def roster_to_dicts(conn, roster_id) -> dict:
    """Rebuild the dict shapes build_grid/recompute_stats consume from frozen rows."""
    hdr = conn.execute("SELECT * FROM rosters WHERE id=?", (roster_id,)).fetchone()
    if hdr is None:
        raise KeyError(roster_id)
    staff = json.loads(hdr["staff_json"])
    technicians = [SimpleNamespace(id=s["id"], name=s["name"],
                                   status=s.get("status", "在籍"),
                                   note=s.get("note", ""),
                                   night_hb=bool(s.get("night_hb", False))) for s in staff]
    day_assignments, night_assignments, requests, on_call = {}, {}, {}, {}
    locked = {}  # (sid, day) -> locked flag of the day row
    for r in conn.execute(
            "SELECT * FROM roster_assignments WHERE roster_id=?", (roster_id,)):
        dn = _day_of(r["date"])
        if r["kind"] == "day":
            if r["location_or_role"] is not None:
                day_assignments.setdefault(dn, {}).setdefault(
                    r["location_or_role"], []).append(r["staff_id"])
            if r["locked"]:
                locked[(r["staff_id"], dn)] = True
        elif r["kind"] == "night":
            night_assignments.setdefault(dn, []).append(r["staff_id"])
        elif r["kind"] == "request":
            requests.setdefault(dn, {})[r["staff_id"]] = r["symbol"]
        elif r["kind"] == "oncall":
            on_call.setdefault(dn, {})[r["location_or_role"]] = r["staff_id"]
    needs = json.loads(hdr["daily_needs_json"] or "{}")
    return {
        "year": hdr["year"], "month": hdr["month"],
        "target_holidays": hdr["target_holidays"],
        "technicians": technicians,
        "day_assignments": day_assignments, "night_assignments": night_assignments,
        "requests": requests, "on_call_assignments": on_call,
        "daily_location_needs": {_day_of(k): v for k, v in needs.items()},
        "locked": locked, "version": hdr["version"], "edit_cursor": hdr["edit_cursor"],
        "status": hdr["status"],
    }
