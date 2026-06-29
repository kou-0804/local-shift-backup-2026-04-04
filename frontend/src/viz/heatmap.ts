import type { RosterState, Row } from '../domain/model';
import type { HeatmapMode } from '../store/uiStore';

const WORK_KINDS = new Set(['work', 'night', 'akemei']);

export function loadByStaff(row: Row): number {
  let n = 0;
  for (const cell of row.cells.values()) if (WORK_KINDS.has(cell.kind)) n += 1;
  return n;
}

// Visualization-only (not authoritative stats): green→red ramp by load fraction.
function loadColor(count: number, max: number): string {
  const t = max <= 0 ? 0 : Math.min(1, count / max);
  const r = Math.round(80 + 175 * t);
  const g = Math.round(200 - 150 * t);
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}66`;
}

export function heatColorForCell(mode: HeatmapMode, state: RosterState, row: Row, day: number): string | null {
  if (mode === 'off') return null;
  if (mode === 'load') {
    const cell = row.cells.get(day);
    if (!cell || !WORK_KINDS.has(cell.kind)) return null;
    const max = Math.max(...state.rows.map(loadByStaff), 1);
    return loadColor(loadByStaff(row), max);
  }
  // shortfall: redden cells whose (day, location) appears in a coverage shortfall
  const cell = row.cells.get(day);
  if (!cell) return null;
  const dd = String(day).padStart(2, '0');
  const hit = state.warnings.coverage.find((w) => w.date.endsWith(`-${dd}`) && cell.text.includes(w.location));
  return hit ? '#ff7043' : null;
}
