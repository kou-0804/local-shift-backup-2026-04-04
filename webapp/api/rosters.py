import calendar
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from shift_scheduler.src.grid_derivation import build_grid
from shift_scheduler.src.stats_engine import recompute_stats, _is_public_off
from shift_scheduler.src.lock_utils import day_locks_from_rows, validate_lock_set


def _month_holidays(year, month):
    """Public holidays for the month as ISO date strings, using the SAME rule as
    stats_engine._is_public_off: Sundays + 祝日(jpholiday) + Jan 1-3. Saturdays
    are NOT public holidays. The UI shades these days."""
    n = calendar.monthrange(year, month)[1]
    return [date(year, month, d).isoformat()
            for d in range(1, n + 1) if _is_public_off(date(year, month, d))]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _iso(year, month, day):
    return date(year, month, day).isoformat()


def _day_of(iso):
    return int(iso.split('-')[2])


def list_rosters(conn) -> list:
    """Roster index for the picker (no ?rid= selected). Read-only header rows,
    newest month first then newest-created so the top row is the likely target.
    Deliberately does NOT build grids/stats — keep this listing cheap."""
    rows = conn.execute(
        "SELECT id, year, month, status, created_at, confirmed_at "
        "FROM rosters ORDER BY year DESC, month DESC, created_at DESC, id DESC"
    ).fetchall()
    return [
        {"id": r["id"], "year": r["year"], "month": r["month"],
         "status": r["status"], "created_at": r["created_at"],
         "confirmed_at": r["confirmed_at"]}
        for r in rows
    ]


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


def _locked_cells(conn, roster_id):
    out = {}
    for r in conn.execute(
            "SELECT staff_id,date,locked FROM roster_assignments "
            "WHERE roster_id=? AND kind='day'", (roster_id,)):
        if r["locked"]:
            out[(r["staff_id"], _day_of(r["date"]))] = True
    return out


def build_roster_grid(conn, roster_id, *, cells=None):
    d = roster_to_dicts(conn, roster_id)
    off = {r["staff_id"]: r["off_count"] for r in conn.execute(
        "SELECT staff_id,off_count FROM roster_meta WHERE roster_id=?", (roster_id,))}
    daikyu = {r["staff_id"]: r["daikyu_count"] for r in conn.execute(
        "SELECT staff_id,daikyu_count FROM roster_meta WHERE roster_id=?", (roster_id,))}
    grid = build_grid(d["year"], d["month"], d["technicians"],
                      d["day_assignments"], d["night_assignments"], d["requests"],
                      off_counts=off, daikyu_counts=daikyu,
                      on_call_assignments=d["on_call_assignments"], cells=cells)
    # Contract reconciliation (P2d): the grid response carries the month's public
    # holidays as ISO strings so the UI can shade them (build_grid already sets
    # top-level year/month).
    grid["holidays"] = _month_holidays(d["year"], d["month"])
    return grid, d


def roster_warnings(d):
    return recompute_stats(
        d["day_assignments"], d["night_assignments"], d["requests"],
        d["technicians"], d["year"], d["month"], d["target_holidays"],
        daily_location_needs=d["daily_location_needs"])


# --- Edit pipeline (assign / unassign / move / toggle_lock) ---


class ConcurrencyError(Exception):
    def __init__(self, grid):
        self.grid = grid


def _has_night(conn, rid, sid, dn, year, month):
    iso = _iso(year, month, dn)
    return conn.execute(
        "SELECT 1 FROM roster_assignments WHERE roster_id=? AND staff_id=? AND date=?"
        " AND kind='night'", (rid, sid, iso)).fetchone() is not None


def _affected(conn, rid, op, payload, year, month):
    sid = payload["staff_id"]
    days = calendar.monthrange(year, month)[1]
    cells = set()

    def add_with_neighbor(dn):
        cells.add((sid, dn))
        if _has_night(conn, rid, sid, dn, year, month):
            if dn < days:
                cells.add((sid, dn + 1))

    if op in ("assign", "unassign", "set_symbol"):
        add_with_neighbor(_day_of(payload["date"]))
    elif op == "move":
        add_with_neighbor(_day_of(payload["from"]["date"]))
        add_with_neighbor(_day_of(payload["to"]["date"]))
    elif op == "toggle_lock":
        cells.add((sid, _day_of(payload["date"])))
    return cells


def _rows_for_cells(conn, rid, cells, year, month):
    out = []
    for sid, dn in sorted(cells):
        iso = _iso(year, month, dn)
        for r in conn.execute(
                "SELECT staff_id,date,kind,location_or_role,symbol,locked "
                "FROM roster_assignments WHERE roster_id=? AND staff_id=? AND date=?",
                (rid, sid, iso)):
            out.append(dict(r))
    return out


def _restore_rows(conn, rid, cells, rows, year, month):
    """Replace all rows for `cells` with the snapshot `rows` (op-agnostic)."""
    for sid, dn in cells:
        conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                     " AND date=?", (rid, sid, _iso(year, month, dn)))
    for r in rows:
        conn.execute(
            "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,"
            "location_or_role,symbol,locked) VALUES(?,?,?,?,?,?,?)",
            (rid, r["staff_id"], r["date"], r["kind"], r["location_or_role"],
             r["symbol"], r["locked"]))


def _mutate(conn, rid, op, payload, year, month):
    sid = payload["staff_id"]
    if op == "assign":
        iso = payload["date"]
        keep = conn.execute(
            "SELECT locked FROM roster_assignments WHERE roster_id=? AND staff_id=?"
            " AND date=? AND kind='day'", (rid, sid, iso)).fetchone()
        locked = keep["locked"] if keep else 0
        conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                     " AND date=? AND kind='day'", (rid, sid, iso))
        conn.execute(
            "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,"
            "location_or_role,locked) VALUES(?,?,?,'day',?,?)",
            (rid, sid, iso, payload["location"], locked))
    elif op == "unassign":
        loc = payload.get("location")
        if loc is not None:
            conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                         " AND date=? AND kind='day' AND location_or_role=?",
                         (rid, sid, payload["date"], loc))
        else:
            conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                         " AND date=? AND kind='day'", (rid, sid, payload["date"]))
    elif op == "move":
        _mutate(conn, rid, "unassign",
                {"staff_id": sid, "date": payload["from"]["date"],
                 "location": payload["from"]["location"]}, year, month)
        _mutate(conn, rid, "assign",
                {"staff_id": sid, "date": payload["to"]["date"],
                 "location": payload["to"]["location"]}, year, month)
    elif op == "toggle_lock":
        loc = payload.get("location")
        cond = " AND location_or_role=?" if loc is not None else ""
        args = [1 if payload["locked"] else 0, rid, sid, payload["date"]]
        if loc is not None:
            args.append(loc)
        n = conn.execute(
            "UPDATE roster_assignments SET locked=? WHERE roster_id=? AND staff_id=?"
            " AND date=? AND kind='day'" + cond, args).rowcount
        if n == 0 and payload["locked"]:   # empty-cell lock sentinel
            conn.execute(
                "INSERT OR IGNORE INTO roster_assignments(roster_id,staff_id,date,kind,"
                "location_or_role,locked) VALUES(?,?,?,'day',NULL,1)",
                (rid, sid, payload["date"]))
    elif op == "set_symbol":
        # The request row (kind='request', location_or_role NULL) carries the cell's
        # 申請 symbol. Replace it wholesale; an empty/None symbol clears the request.
        iso = payload["date"]
        sym = payload.get("symbol")
        conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                     " AND date=? AND kind='request'", (rid, sid, iso))
        if sym:
            conn.execute(
                "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,"
                "location_or_role,symbol,locked) VALUES(?,?,?,'request',NULL,?,0)",
                (rid, sid, iso, sym))


def _changed_cells(conn, rid, grid, cells, year, month):
    by_staff = {r["staff_id"]: r for r in grid["rows"]}
    locked = _locked_cells(conn, rid)
    out = []
    for sid, dn in sorted(cells):
        row = by_staff.get(sid)
        if row is None:
            continue
        out.append({
            "staff_id": sid, "date": _iso(year, month, dn),
            "text": row["cells"][dn], "category": row["cell_meta"][dn]["kind"],
            "fill": row["cell_meta"][dn]["fill"],
            "locked": bool(locked.get((sid, dn), False)), "warnings": []})
    return out


def _recompute_and_persist(conn, rid, affected_staff):
    d = roster_to_dicts(conn, rid)
    warnings = recompute_stats(
        d["day_assignments"], d["night_assignments"], d["requests"],
        d["technicians"], d["year"], d["month"], d["target_holidays"],
        daily_location_needs=d["daily_location_needs"])
    grid = build_grid(d["year"], d["month"], d["technicians"],
                      d["day_assignments"], d["night_assignments"], d["requests"],
                      off_counts=warnings["off_counts"],
                      daikyu_counts=warnings["daikyu_counts"],
                      cells={(s, 1) for s in affected_staff})
    for r in grid["rows"]:
        sid = r["staff_id"]
        conn.execute(
            "INSERT OR REPLACE INTO roster_meta(roster_id,staff_id,off_count,"
            "daikyu_count,stats_json) VALUES(?,?,?,?,?)",
            (rid, sid, float(warnings["off_counts"].get(sid, 0)),
             float(warnings["daikyu_counts"].get(sid, 0)),
             json.dumps(r["stats"] or {}, ensure_ascii=False)))
    return warnings, grid, d


def _warnings_payload(warnings):
    return {
        "coverage": warnings["coverage"],
        "holiday_deficit": warnings["holiday_deficit"],
        "consecutive": warnings["consecutive"],
        "night_hb_gaps": warnings["night_hb_gaps"],
        "skill": []}  # P3 placeholder (needs skills/PB masters)


def apply_edit(conn, rid, payload, *, user_id=None):
    hdr = conn.execute("SELECT version,edit_cursor,year,month FROM rosters WHERE id=?",
                       (rid,)).fetchone()
    if hdr is None:
        raise KeyError(rid)
    year, month = hdr["year"], hdr["month"]
    if payload.get("expected_version") != hdr["version"]:
        grid, d = build_roster_grid(conn, rid)
        raise ConcurrencyError({"version": hdr["version"], "grid": grid,
                                "warnings": roster_warnings(d)})

    op = payload["op"]
    cells = _affected(conn, rid, op, payload, year, month)
    before = _rows_for_cells(conn, rid, cells, year, month)
    _mutate(conn, rid, op, payload, year, month)
    # re-evaluate affected cells AFTER mutation (night row may have appeared/left)
    cells |= _affected(conn, rid, op, payload, year, month)
    after = _rows_for_cells(conn, rid, cells, year, month)

    cursor = hdr["edit_cursor"]
    conn.execute("DELETE FROM roster_edits WHERE roster_id=? AND seq>?", (rid, cursor))
    seq = cursor + 1
    cur = conn.execute(
        "INSERT INTO roster_edits(roster_id,seq,user_id,at,op,payload_json,"
        "before_json,after_json) VALUES(?,?,?,?,?,?,?,?)",
        (rid, seq, user_id, _now(), op, json.dumps(payload, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False)))
    edit_id = cur.lastrowid
    new_version = hdr["version"] + 1
    conn.execute("UPDATE rosters SET version=?, edit_cursor=? WHERE id=?",
                 (new_version, seq, rid))

    affected_staff = {sid for sid, _ in cells}
    warnings, _, _ = _recompute_and_persist(conn, rid, affected_staff)
    grid, _ = build_roster_grid(conn, rid, cells=cells)
    changed = _changed_cells(conn, rid, grid, cells, year, month)
    stats = {r["staff_id"]: r["stats"] for r in grid["rows"]}
    conn.commit()

    redo = conn.execute(
        "SELECT 1 FROM roster_edits WHERE roster_id=? AND seq=? AND undone=1",
        (rid, seq + 1)).fetchone() is not None
    return {
        "edit_id": edit_id, "seq": seq, "version": new_version,
        "changed_cells": changed, "stats": stats,
        "warnings": _warnings_payload(warnings),
        "undo_available": seq > 0, "redo_available": redo}


# --- Undo / Redo (linear history + cursor; full-row snapshots) ---


def _undo_redo(conn, rid, payload, *, redo):
    hdr = conn.execute("SELECT version,edit_cursor,year,month FROM rosters WHERE id=?",
                       (rid,)).fetchone()
    if hdr is None:
        raise KeyError(rid)
    year, month = hdr["year"], hdr["month"]
    if payload.get("expected_version") != hdr["version"]:
        grid, d = build_roster_grid(conn, rid)
        raise ConcurrencyError({"version": hdr["version"], "grid": grid,
                                "warnings": roster_warnings(d)})
    cursor = hdr["edit_cursor"]
    target_seq = cursor + 1 if redo else cursor
    if target_seq <= 0:
        raise ConcurrencyError({"version": hdr["version"], "reason": "nothing to undo"})
    edit = conn.execute(
        "SELECT * FROM roster_edits WHERE roster_id=? AND seq=? AND undone=?",
        (rid, target_seq, 0 if not redo else 1)).fetchone()
    if edit is None:
        raise ConcurrencyError({"version": hdr["version"],
                                "reason": "nothing to redo" if redo else "nothing to undo"})

    snap = json.loads(edit["after_json"] if redo else edit["before_json"])
    cells = {(r["staff_id"], _day_of(r["date"])) for r in
             json.loads(edit["before_json"]) + json.loads(edit["after_json"])}
    _restore_rows(conn, rid, cells, snap, year, month)
    conn.execute("UPDATE roster_edits SET undone=? WHERE id=?",
                 (0 if redo else 1, edit["id"]))
    new_cursor = cursor + 1 if redo else cursor - 1
    new_version = hdr["version"] + 1
    conn.execute("UPDATE rosters SET version=?, edit_cursor=? WHERE id=?",
                 (new_version, new_cursor, rid))

    affected_staff = {sid for sid, _ in cells}
    warnings, _, _ = _recompute_and_persist(conn, rid, affected_staff)
    grid, _ = build_roster_grid(conn, rid, cells=cells)
    changed = _changed_cells(conn, rid, grid, cells, year, month)
    stats = {r["staff_id"]: r["stats"] for r in grid["rows"]}
    conn.commit()
    redo_avail = conn.execute(
        "SELECT 1 FROM roster_edits WHERE roster_id=? AND seq=? AND undone=1",
        (rid, new_cursor + 1)).fetchone() is not None
    return {
        "edit_id": edit["id"], "seq": new_cursor, "version": new_version,
        "changed_cells": changed, "stats": stats,
        "warnings": _warnings_payload(warnings),
        "undo_available": new_cursor > 0, "redo_available": redo_avail}


def undo(conn, rid, payload):
    return _undo_redo(conn, rid, payload, redo=False)


def redo(conn, rid, payload):
    return _undo_redo(conn, rid, payload, redo=True)


# --- P2b: partial-lock re-solve (resolve_roster + synthetic op='resolve' edit) ---


class LockConflictError(Exception):
    """Raised when a lock set is structurally impossible (pre-validate) or collides
    with a hard constraint (solver assumption-infeasibility). Surfaced as HTTP 422."""

    def __init__(self, conflicts):
        self.conflicts = conflicts


def _all_day_rows_snapshot(conn, rid):
    """Full roster_assignments rows (all kinds) in the column shape _restore_rows
    consumes — the before/after snapshot for the undoable resolve edit."""
    return [dict(r) for r in conn.execute(
        "SELECT staff_id,date,kind,location_or_role,symbol,locked "
        "FROM roster_assignments WHERE roster_id=?", (rid,))]


def _resolve_rows_from_result(result):
    """Mirror freeze_roster's row build (day/night/oncall/request), locked=0.
    Yields (staff_id, iso_date, kind, location_or_role, symbol, locked)."""
    y, m = result.year, result.month
    rows = []
    for d, locs in result.day_assignments.items():
        for loc, ids in locs.items():
            for sid in ids:
                rows.append((sid, _iso(y, m, int(d)), "day", loc, None, 0))
    for d, ids in result.night_assignments.items():
        for sid in ids:
            rows.append((sid, _iso(y, m, int(d)), "night", "夜", None, 0))
    for d, sm in result.requests.items():
        for sid, sym in sm.items():
            rows.append((sid, _iso(y, m, int(d)), "request", None, sym, 0))
    for d, roles in (result.on_call_assignments or {}).items():
        for role, sid in roles.items():
            rows.append((sid, _iso(y, m, int(d)), "oncall", role, None, 0))
    return rows


def resolve_roster(conn, rid, *, runner, user_id=None) -> dict:
    """Re-run the solver holding locked=1 day cells fixed, then re-freeze and record
    a synthetic undoable op='resolve' edit. Serialised via jobs._solve_lock (protects
    CP-SAT determinism, seed=42/num_workers=1). 404 (KeyError) if missing; raises
    LockConflictError (-> 422) on structural-impossible or hard-conflict lock sets."""
    hdr = conn.execute(
        "SELECT year,month,data_dir,target_holidays,version,edit_cursor "
        "FROM rosters WHERE id=?", (rid,)).fetchone()
    if hdr is None:
        raise KeyError(rid)
    year, month = hdr["year"], hdr["month"]

    locked_rows = [dict(r) for r in conn.execute(
        "SELECT staff_id,date,kind,location_or_role,locked FROM roster_assignments "
        "WHERE roster_id=? AND kind='day' AND locked=1", (rid,))]
    la = day_locks_from_rows(locked_rows)

    # (1) Pre-validate (fast, pure) -> 422 before any solve.
    d_dicts = roster_to_dicts(conn, rid)
    errs = validate_lock_set(la, daily_location_needs=d_dicts["daily_location_needs"])
    if errs:
        raise LockConflictError({"stage": "pre_validate", "errors": errs})

    before = _all_day_rows_snapshot(conn, rid)

    # (2) Re-solve serialised.
    from webapp.api.jobs import _solve_lock
    with _solve_lock:
        result = runner(year, month, hdr["data_dir"], locked_assignments=la)

    # (3) Hard-constraint collision -> 422 with the exact offending cells.
    conflicts = getattr(result, "lock_conflicts", []) or []
    if conflicts:
        raise LockConflictError({"stage": "solve", "conflicts": conflicts})

    # (4) Re-freeze: keep locked day rows verbatim; delete + replace all unlocked rows.
    locked_keys = {(r["staff_id"], r["date"]) for r in locked_rows}
    conn.execute(
        "DELETE FROM roster_assignments WHERE roster_id=? AND NOT (kind='day' AND locked=1)",
        (rid,))
    for sid, iso, kind, lor, sym, lk in _resolve_rows_from_result(result):
        if kind == "day" and (sid, iso) in locked_keys:
            continue  # keep the locked version verbatim
        conn.execute(
            "INSERT OR IGNORE INTO roster_assignments(roster_id,staff_id,date,kind,"
            "location_or_role,symbol,locked) VALUES(?,?,?,?,?,?,?)",
            (rid, sid, iso, kind, lor, sym, lk))

    after = _all_day_rows_snapshot(conn, rid)

    # (5) Synthetic undoable op='resolve' edit (full-row before/after snapshots, so a
    # single undo restores the complete pre-resolve grid via _restore_rows).
    cursor = hdr["edit_cursor"]
    conn.execute("DELETE FROM roster_edits WHERE roster_id=? AND seq>?", (rid, cursor))
    seq = cursor + 1
    payload = {"locked": sorted([list(k) for k in locked_keys])}
    conn.execute(
        "INSERT INTO roster_edits(roster_id,seq,user_id,at,op,payload_json,"
        "before_json,after_json) VALUES(?,?,?,?,?,?,?,?)",
        (rid, seq, user_id, _now(), "resolve",
         json.dumps(payload, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False),
         json.dumps(after, ensure_ascii=False)))
    new_version = hdr["version"] + 1
    conn.execute("UPDATE rosters SET version=?, edit_cursor=? WHERE id=?",
                 (new_version, seq, rid))

    # (6) Recompute stats + grid, commit, return.
    affected_staff = {r["staff_id"] for r in before + after}
    warnings, _, _ = _recompute_and_persist(conn, rid, affected_staff)
    grid, _ = build_roster_grid(conn, rid)
    conn.commit()
    return {
        "version": new_version,
        "grid": grid,
        "warnings": _warnings_payload(warnings),
        "unlockable": getattr(result, "unlockable_locks", []),
    }
