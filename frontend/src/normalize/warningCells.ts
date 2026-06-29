import type {
  CoverageWarning,
  SkillWarning,
  ConsecutiveWarning,
  HolidayDeficitWarning,
} from '../domain/wire';
import type { RosterState } from '../domain/model';
import type { CellRef } from '../store/uiStore';
import { parseDayFromIso } from './dates';

// coverage is location/day scoped → highlight every staff row at that day.
export const cellsForCoverage = (w: CoverageWarning, state: RosterState): CellRef[] => {
  const day = parseDayFromIso(w.date);
  return state.rows.map((r) => ({ staffId: r.staffId, day }));
};

export const cellsForSkill = (w: SkillWarning): CellRef[] => [
  { staffId: w.staff_id, day: parseDayFromIso(w.date) },
];

export const cellsForConsecutive = (w: ConsecutiveWarning): CellRef[] => {
  const start = parseDayFromIso(w.start);
  return Array.from({ length: w.len }, (_, i) => ({ staffId: w.staff_id, day: start + i }));
};

export const cellsForHolidayDeficit = (w: HolidayDeficitWarning, state: RosterState): CellRef[] => {
  const row = state.rows.find((r) => r.staffId === w.staff_id);
  return row ? Array.from(row.cells.keys()).map((day) => ({ staffId: w.staff_id, day })) : [];
};
