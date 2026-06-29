import type { WireRosterResponse } from '../domain/wire';
import type { RosterState, Row, Cell, OnCallRow } from '../domain/model';
import { normalizeFill } from './fill';
import { parseDayFromIso } from './dates';
import { normalizeWarnings } from './warnings';

const computeDaysInMonth = (year: number, month: number) => new Date(year, month, 0).getDate();

/** Map the nested GET /rosters/{rid} response into the flat client RosterState. */
export function normalizeGrid(rosterId: string, w: WireRosterResponse): RosterState {
  const grid = w.grid;

  const rows: Row[] = grid.rows.map((wr) => {
    const cells = new Map<number, Cell>();
    for (const [dayStr, text] of Object.entries(wr.cells)) {
      const day = Number(dayStr);
      const meta = wr.cell_meta[dayStr] ?? { kind: 'empty', fill: null };
      cells.set(day, {
        day,
        text,
        kind: meta.kind,
        fill: normalizeFill(meta.fill),
        locked: meta.locked ?? false,
      });
    }
    return {
      staffId: wr.staff_id,
      staffNum: wr.staff_num,
      name: wr.name,
      cells,
      hasWork: wr.has_work,
      stats: wr.stats,
    };
  });

  const oncallRows: OnCallRow[] = grid.oncall_rows.map((o) => ({
    label: o.label,
    cells: new Map(Object.entries(o.cells).map(([d, v]) => [Number(d), v])),
  }));

  const weekdays: Record<number, string> = {};
  for (const [d, c] of Object.entries(grid.weekdays)) weekdays[Number(d)] = c;

  const holidays = new Set<number>((grid.holidays ?? []).map(parseDayFromIso));

  const year = w.year ?? grid.year;
  const month = w.month ?? grid.month;

  return {
    rosterId,
    year,
    month,
    daysInMonth: grid.days_in_month ?? computeDaysInMonth(year, month),
    version: w.version,
    status: w.status,
    rows,
    oncallRows,
    weekdays,
    holidays,
    statsColumns: grid.stats_columns,
    warnings: normalizeWarnings(w.warnings),
    undoAvailable: false,
    redoAvailable: false,
  };
}
