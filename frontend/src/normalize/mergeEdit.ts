import type { RosterState, Row, Cell } from '../domain/model';
import type { WireEditResponse } from '../domain/wire';
import type { EditOp } from '../domain/editOps';
import { parseDayFromIso } from './dates';
import { normalizeFill, localFillFor } from './fill';
import { normalizeWarnings } from './warnings';

/** Merge the AUTHORITATIVE server edit response. Overwrites changed cells (incl.
 *  the D+1 明け cell the client cannot predict), affected-staff stats, the whole
 *  warning set, version, and undo/redo flags. Never recompute stats locally. */
export function mergeEditResponse(state: RosterState, resp: WireEditResponse): RosterState {
  const changedByStaff = new Map<string, Cell[]>();
  for (const c of resp.changed_cells) {
    const cell: Cell = {
      day: parseDayFromIso(c.date),
      text: c.text,
      kind: c.category, // naming asymmetry: edit `category` → client `kind`
      fill: normalizeFill(c.fill),
      locked: c.locked,
    };
    const arr = changedByStaff.get(c.staff_id) ?? [];
    arr.push(cell);
    changedByStaff.set(c.staff_id, arr);
  }

  const rows: Row[] = state.rows.map((r) => {
    const changed = changedByStaff.get(r.staffId);
    const hasStats = Object.prototype.hasOwnProperty.call(resp.stats, r.staffId);
    if (!changed && !hasStats) return r;

    let cells = r.cells;
    if (changed) {
      cells = new Map(r.cells);
      for (const c of changed) cells.set(c.day, c); // pending implicitly cleared
    }
    let stats = r.stats;
    let hasWork = r.hasWork;
    if (hasStats) {
      const ns = resp.stats[r.staffId];
      stats = ns;
      hasWork = ns !== null;
    }
    return { ...r, cells, stats, hasWork };
  });

  return {
    ...state,
    rows,
    version: resp.version,
    warnings: normalizeWarnings(resp.warnings),
    undoAvailable: resp.undo_available,
    redoAvailable: resp.redo_available,
  };
}

/** Thin optimistic update of the edited cell text/fill ONLY. Stats stay until the merge. */
export function applyOptimistic(state: RosterState, op: EditOp): RosterState {
  const sid = op.staff_id;
  const rows = state.rows.map((r) => {
    if (r.staffId !== sid) return r;

    const cells = new Map(r.cells);
    const setCell = (day: number, text: string) => {
      const prev = cells.get(day);
      cells.set(day, {
        day,
        text,
        kind: prev?.kind ?? 'work',
        fill: localFillFor(text),
        locked: prev?.locked ?? false,
        pending: true,
      });
    };
    if (op.op === 'assign') setCell(parseDayFromIso(op.date), op.location);
    else if (op.op === 'unassign') setCell(parseDayFromIso(op.date), '');
    else if (op.op === 'move') {
      const fromDay = parseDayFromIso(op.from.date);
      const toDay = parseDayFromIso(op.to.date);
      const moving = cells.get(fromDay)?.text ?? op.to.location ?? '';
      setCell(fromDay, '');
      setCell(toDay, moving);
    } else if (op.op === 'toggle_lock') {
      const day = parseDayFromIso(op.date);
      const prev = cells.get(day);
      if (prev) cells.set(day, { ...prev, locked: op.locked });
    } else if (op.op === 'set_symbol') {
      setCell(parseDayFromIso(op.date), op.symbol ?? '');
    }
    return { ...r, cells };
  });
  return { ...state, rows };
}

/** dnd-kit drop → one `move` op with nested {date,location} endpoints. The moved
 *  assignment's location is carried on both endpoints (day shift of one cell).
 *  Cross-staff, same-cell, or empty source → null (no single move). */
export function buildMovePayload(
  sourceId: string,
  targetId: string,
  year: number,
  month: number,
  location: string,
): Extract<EditOp, { op: 'move' }> | null {
  const [sSid, sDay] = sourceId.split(':');
  const [tSid, tDay] = targetId.split(':');
  if (sSid !== tSid || sDay === tDay) return null;
  if (!location) return null;
  const pad = (n: string) => n.padStart(2, '0');
  const iso = (d: string) => `${year}-${pad(String(month))}-${pad(d)}`;
  return {
    op: 'move',
    staff_id: sSid,
    from: { date: iso(sDay), location },
    to: { date: iso(tDay), location },
  };
}
