import { describe, it, expect } from 'vitest';
import { cellsForCoverage, cellsForSkill, cellsForConsecutive } from './warningCells';
import { normalizeGrid } from './normalizeGrid';
import { gridFixture } from '../test/fixtures';

const state = normalizeGrid('R1', gridFixture);

describe('warningCells', () => {
  it('maps a coverage warning to the day column for every staff', () => {
    const cells = cellsForCoverage({ date: '2026-06-01', location: 'ク', required: 3, assigned: 2, short: 1 }, state);
    expect(cells).toEqual([
      { staffId: 'T013', day: 1 },
      { staffId: 'T020', day: 1 },
    ]);
  });
  it('maps a skill warning to the single (staff, day) cell', () => {
    expect(
      cellsForSkill({ date: '2026-06-16', location: '心', staff_id: 'T013', rule: 'min_rank', need: 'B', have: 'C' }),
    ).toEqual([{ staffId: 'T013', day: 16 }]);
  });
  it('maps a consecutive warning to the run of days', () => {
    expect(cellsForConsecutive({ staff_id: 'T013', start: '2026-06-10', len: 3 })).toEqual([
      { staffId: 'T013', day: 10 },
      { staffId: 'T013', day: 11 },
      { staffId: 'T013', day: 12 },
    ]);
  });
});
