import { describe, it, expect } from 'vitest';
import { loadByStaff, heatColorForCell } from './heatmap';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { gridFixture } from '../test/fixtures';

const state = normalizeGrid('R1', gridFixture);
const t13 = state.rows.find((r) => r.staffId === 'T013')!;

describe('heatmap', () => {
  it('counts work-bearing cells per staff (work/night/akemei, not off/empty)', () => {
    // T013: day1 work, day2 akemei, day3 night, day4 empty → 3 work-days
    expect(loadByStaff(t13)).toBe(3);
  });
  it('returns null in off mode (base fill wins)', () => {
    expect(heatColorForCell('off', state, t13, 3)).toBeNull();
  });
  it('returns a load color on work cells in load mode', () => {
    const c = heatColorForCell('load', state, t13, 1);
    expect(c).toMatch(/^#/);
  });
  it('returns a shortfall color only where coverage warns that day/location in shortfall mode', () => {
    const s2 = {
      ...state,
      warnings: {
        ...state.warnings,
        coverage: [{ date: '2026-06-01', location: 'CT', required: 2, assigned: 1, short: 1 }],
      },
    };
    expect(heatColorForCell('shortfall', s2, t13, 1)).toMatch(/^#/); // day1 cell text 'CT' matches location
    expect(heatColorForCell('shortfall', s2, t13, 3)).toBeNull();
  });
});
