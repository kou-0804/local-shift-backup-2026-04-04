import type {
  CoverageWarning,
  HolidayDeficitWarning,
  ConsecutiveWarning,
  SkillWarning,
  NightHbGap,
} from './wire';

/** Stable client-side warning shape. The wire sends different groups on GET vs
 *  edit responses; the normalizer always produces this full, defaulted shape. */
export interface ClientWarnings {
  coverage: CoverageWarning[];
  holiday_deficit: HolidayDeficitWarning[];
  consecutive: ConsecutiveWarning[];
  skill: SkillWarning[];
  night_hb_gaps: NightHbGap[];
  off_counts: Record<string, number>;
  daikyu_counts: Record<string, number>;
}

export interface Cell {
  day: number;
  text: string;
  kind: string; // unified: grid `kind` OR edit `category`
  fill: string | null; // normalized "#RRGGBB" or null
  locked: boolean;
  pending?: boolean; // optimistic, awaiting server confirmation
}

export interface Row {
  staffId: string;
  staffNum: number;
  name: string;
  cells: Map<number, Cell>;
  hasWork: boolean;
  stats: Record<string, number> | null;
}

export interface OnCallRow {
  label: string;
  cells: Map<number, string>;
}

export interface RosterState {
  rosterId: string;
  year: number;
  month: number;
  daysInMonth: number;
  version: number;
  status?: string;
  rows: Row[];
  oncallRows: OnCallRow[];
  weekdays: Record<number, string>; // {1:"月",...}
  holidays: Set<number>; // day numbers flagged 祝
  statsColumns: string[];
  warnings: ClientWarnings;
  undoAvailable: boolean;
  redoAvailable: boolean;
}
