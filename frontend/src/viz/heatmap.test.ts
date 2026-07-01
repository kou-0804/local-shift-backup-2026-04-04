import { describe, it, expect } from 'vitest';
import { loadByStaff, heatColorForCell, deviationColor } from './heatmap';
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
  it('偏り: above-average → red, below-average → blue, near-average → light', () => {
    const rOf = (hex: string) => parseInt(hex.slice(1, 3), 16);
    const bOf = (hex: string) => parseInt(hex.slice(5, 7), 16);
    const above = deviationColor(25, 20, 5); // +1 → red
    const below = deviationColor(15, 20, 5); // -1 → blue
    const near = deviationColor(20, 20, 5); // 0 → neutral
    expect(rOf(above)).toBeGreaterThan(rOf(below)); // more red when above average
    expect(bOf(below)).toBeGreaterThan(bOf(above)); // more blue when below average
    expect(near.toLowerCase()).toBe('#f1f5f9'); // neutral at the mean
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
