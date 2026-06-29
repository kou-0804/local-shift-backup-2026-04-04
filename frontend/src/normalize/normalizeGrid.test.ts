import { describe, it, expect } from 'vitest';
import { normalizeGrid } from './normalizeGrid';
import { gridFixture } from '../test/fixtures';

describe('normalizeGrid', () => {
  it('maps the nested wire grid into RosterState with normalized fills and day-int keys', () => {
    const s = normalizeGrid('R1', gridFixture);
    expect(s.rosterId).toBe('R1');
    expect(s.version).toBe(4);
    expect(s.daysInMonth).toBe(30); // June 2026
    expect(s.weekdays[1]).toBe('月');
    const t13 = s.rows.find((r) => r.staffId === 'T013')!;
    expect(t13.cells.get(3)).toEqual({ day: 3, text: '病CT夜', kind: 'night', fill: '#FFFF00', locked: true });
    expect(t13.cells.get(1)!.fill).toBeNull();
    expect(t13.stats!['CT']).toBe(7);
    const t20 = s.rows.find((r) => r.staffId === 'T020')!;
    expect(t20.hasWork).toBe(false);
    expect(t20.stats).toBeNull();
  });

  it('flags holidays from the grid holidays array', () => {
    const s = normalizeGrid('R1', {
      ...gridFixture,
      grid: { ...gridFixture.grid, holidays: ['2026-06-02'] },
    });
    expect(s.holidays.has(2)).toBe(true);
  });

  it('defaults all warning groups to a stable client shape', () => {
    const s = normalizeGrid('R1', { ...gridFixture, warnings: {} });
    expect(s.warnings.coverage).toEqual([]);
    expect(s.warnings.skill).toEqual([]);
    expect(s.warnings.night_hb_gaps).toEqual([]);
    expect(s.warnings.off_counts).toEqual({});
  });
});
