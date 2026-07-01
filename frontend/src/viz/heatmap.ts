import type { RosterState, Row } from '../domain/model';
import type { HeatmapMode } from '../store/uiStore';

const WORK_KINDS = new Set(['work', 'night', 'akemei']);

export function loadByStaff(row: Row): number {
  let n = 0;
  for (const cell of row.cells.values()) if (WORK_KINDS.has(cell.kind)) n += 1;
  return n;
}

/** Fairness view stats: mean work-days over *working* staff plus a symmetric
 *  spread (max absolute deviation) used to scale the blue↔red ramp. Fraction-of-max
 *  (the old 負荷 view) was useless here — everyone works ~the same number of days, so
 *  every cell pinned to the red end. Deviation-from-average gives real contrast. */
export function fairnessStats(state: RosterState): { mean: number; spread: number } {
  const loads = state.rows.map(loadByStaff).filter((n) => n > 0);
  if (loads.length === 0) return { mean: 0, spread: 0 };
  const mean = loads.reduce((a, b) => a + b, 0) / loads.length;
  const spread = Math.max(1, ...loads.map((n) => Math.abs(n - mean)));
  return { mean, spread };
}

const NEUTRAL = [241, 245, 249]; // 平均付近: 薄いスレート
const WARM = [239, 68, 68]; // 平均より多い: 赤
const COOL = [59, 130, 246]; // 平均より少ない: 青

/** Deviation-from-average color: below→blue, near→light, above→red. */
export function deviationColor(load: number, mean: number, spread: number): string {
  const t = spread <= 0 ? 0 : Math.max(-1, Math.min(1, (load - mean) / spread));
  const target = t >= 0 ? WARM : COOL;
  const a = Math.abs(t);
  const ch = (i: number) => Math.round(NEUTRAL[i] + (target[i] - NEUTRAL[i]) * a);
  return `#${[0, 1, 2].map((i) => ch(i).toString(16).padStart(2, '0')).join('')}`;
}

export function heatColorForCell(mode: HeatmapMode, state: RosterState, row: Row, day: number): string | null {
  if (mode === 'off') return null;
  if (mode === 'load') {
    // 偏り(公平性): 各技師の勤務日数が平均からどれだけ離れているかを色化
    // （平均より多い=赤 / 少ない=青 / 平均付近=薄色）。
    const cell = row.cells.get(day);
    if (!cell || !WORK_KINDS.has(cell.kind)) return null;
    const { mean, spread } = fairnessStats(state);
    return deviationColor(loadByStaff(row), mean, spread);
  }
  // shortfall: redden cells whose (day, location) appears in a coverage shortfall
  const cell = row.cells.get(day);
  if (!cell) return null;
  const dd = String(day).padStart(2, '0');
  const hit = state.warnings.coverage.find((w) => w.date.endsWith(`-${dd}`) && cell.text.includes(w.location));
  return hit ? '#ff7043' : null;
}
