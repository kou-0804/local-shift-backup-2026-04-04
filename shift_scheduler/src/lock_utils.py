"""Pure, solver-free helpers for P2b partial-lock re-solve.

Shared by the schedulers (day/night lock injection), the post-processors
(`reassert_locks` safety net), and the web `/resolve` builder. No CP-SAT, no I/O —
everything here is fast-unit-testable.

Lock-set shape (single structure threaded to both schedulers)::

    locked_assignments: dict[datetime.date, {
        'force':  set[tuple[str, str]],   # {(staff_id, loc_code)}
        'forbid': set[tuple[str, str]],   # {(staff_id, loc_code)}
    }]

Day-domain entries use a real day ``loc_code`` (incl. OFF-lock ``'休'``/``'○'``).
Night-domain entries use ``loc_code == '夜'`` (NIGHT_LOC). In P2b ``/resolve`` emits
day-domain locks only.
"""
from datetime import date

from shift_scheduler.src.models.assignment import DayAssignment
from shift_scheduler.src.models.skill import SkillRank

NIGHT_LOC = '夜'          # night-domain lock marker (occupancy only)
OFF_LOCS = {'休', '○'}    # OFF-lock location codes (no BoolVar)


def day_locks_from_rows(rows):
    """Build a ``locked_assignments`` dict from frozen ``roster_assignments`` rows.

    Only ``kind == 'day'`` rows with a truthy ``locked`` flag contribute. A real
    work location becomes a ``force`` on that (sid, loc); an empty-cell sentinel
    (``location_or_role is None``) or an OFF code (``'休'``/``'○'``) becomes an
    OFF-lock force on (sid, '休'). Night rows are never UI-lockable in v1 and are
    skipped. The date string is converted to ``datetime.date`` at this boundary.
    """
    out: dict = {}
    for row in rows:
        if row.get('kind') != 'day' or not row.get('locked'):
            continue
        d = date.fromisoformat(row['date'])
        loc = row.get('location_or_role')
        if loc == NIGHT_LOC:
            continue  # night not UI-lockable in v1
        bucket = out.setdefault(d, {'force': set(), 'forbid': set()})
        if loc is None or loc in OFF_LOCS:
            bucket['force'].add((row['staff_id'], '休'))   # OFF-lock
        else:
            bucket['force'].add((row['staff_id'], loc))
    return out


def validate_lock_set(locked_assignments, daily_location_needs):
    """Fast, pure structural pre-check. Returns a list of human-readable error
    strings (``[]`` when clean). Catches the impossibilities cheaply, before any
    solver is invoked; the in-solver assumption diagnostics catch the genuinely
    hard-constraint collisions.

    Checks per date:
      * <=1 *work* force per (staff, date); a work force + an OFF force for the
        same staff/day is a contradiction.
      * per (date, loc) (loc not OFF/'夜', not parenthesized): #forced <=
        daily_location_needs.get(day, {}).get(loc)  (cap skipped when unknown).
      * a (sid, loc) present in both force and forbid for the same date.
    """
    errs: list = []
    needs = daily_location_needs or {}
    for d, locks in (locked_assignments or {}).items():
        iso = d.isoformat() if isinstance(d, date) else str(d)
        force = locks.get('force', set()) or set()
        forbid = locks.get('forbid', set()) or set()

        # per-staff: <=1 work force; no work+off contradiction.
        by_staff: dict = {}
        for sid, lc in force:
            if lc == NIGHT_LOC:
                continue
            by_staff.setdefault(sid, []).append(lc)
        for sid, locs in by_staff.items():
            work = [lc for lc in locs if lc not in OFF_LOCS]
            off = [lc for lc in locs if lc in OFF_LOCS]
            if len(work) > 1:
                errs.append(
                    f"{iso}: {sid} に複数の勤務地が同時に強制されています ({', '.join(sorted(work))})")
            if work and off:
                errs.append(
                    f"{iso}: {sid} に勤務({', '.join(sorted(work))})と休みが同時に強制されています")

        # per (loc): forced count must fit the day's need (when known).
        per_loc: dict = {}
        for sid, lc in force:
            if lc in OFF_LOCS or lc == NIGHT_LOC:
                continue
            if lc.startswith('(') and lc.endswith(')'):
                continue
            per_loc.setdefault(lc, 0)
            per_loc[lc] += 1
        day_needs = needs.get(d.day if isinstance(d, date) else d, {}) or {}
        for lc, cnt in per_loc.items():
            cap = day_needs.get(lc)
            if cap is not None and cnt > cap:
                errs.append(
                    f"{iso}: [{lc}] への強制配置数({cnt})が必要数({cap})を超えています")

        # same (sid, loc) forced and forbidden.
        for cell in force & forbid:
            errs.append(f"{iso}: {cell[0]}/{cell[1]} が force と forbid の両方に指定されています")
    return errs


def reassert_locks(day_result_list, locked_assignments, year, month):
    """Safety net: guarantee every locked (staff_id, date) ends up at exactly its
    locked location, regardless of what a post-processor did. Repositions ONLY the
    locked staff's own (sid, date) rows (removes that staff from any other location
    that day, ensures the locked location/休 present); other staff are untouched.

    Rank is set to ``SkillRank.NONE`` — reassert is a safety net and the downstream
    ``recompute_stats`` / grid derivation operate on the day_assignments dict and do
    not depend on the DayAssignment rank.
    """
    if not locked_assignments:
        return day_result_list
    # pin[(sid, date)] = target loc_code (OFF -> canonical '休'); skip night locks.
    pin: dict = {}
    for d, locks in locked_assignments.items():
        for sid, lc in (locks.get('force', set()) or set()):
            if lc == NIGHT_LOC:
                continue
            pin[(sid, d)] = '休' if lc in OFF_LOCS else lc
    if not pin:
        return day_result_list

    out = [da for da in day_result_list if (da.staff_id, da.date) not in pin]
    for (sid, d), loc in pin.items():
        out.append(DayAssignment(
            date=d, staff_id=sid, location_code=loc, rank=SkillRank.NONE))
    return out
