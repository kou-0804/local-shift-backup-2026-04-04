// Exact server wire shapes — do NOT use these in components; normalize first.
//
// Authoritative P2a contract:
//  - GET /rosters/{rid}        → { version, status, year, month, grid, warnings }
//  - GET /rosters/{rid}/grid   → the bare `grid` object
//  - POST .../edits|undo|redo  → WireEditResponse | 409 (FastAPI `detail` envelope)
// All integer dict keys ("1".."31") are STRINGS over JSON.

export interface WireCellMeta {
  kind: string;
  fill: string | null;
  locked?: boolean; // absent on initial grid load → defaults false
}

export interface WireRow {
  staff_id: string;
  staff_num: number;
  name: string;
  cells: Record<string, string>; // {"1":"CT","2":"○"}
  cell_meta: Record<string, WireCellMeta>; // {"1":{kind,fill}}
  has_work: boolean;
  stats: Record<string, number> | null; // 21 cols, or null when !has_work
}

export interface WireOnCallRow {
  label: string;
  cells: Record<string, string>;
}

// --- warning item shapes ---
export interface CoverageWarning {
  date: string;
  location: string;
  required: number;
  assigned: number;
  short: number;
}
export interface HolidayDeficitWarning {
  staff_id: string;
  off: number;
  target: number;
  short: number;
}
export interface ConsecutiveWarning {
  staff_id: string;
  start: string;
  len: number;
}
export interface SkillWarning {
  date: string;
  location: string;
  staff_id: string;
  rule: string;
  need: string;
  have: string;
}
// night_hb_gaps is backend-defined; keep permissive but carry common fields.
export interface NightHbGap {
  date?: string;
  rank?: string;
  [k: string]: unknown;
}

// GET warnings carry off_counts/daikyu_counts (maps) + coverage/holiday_deficit/
// consecutive/night_hb_gaps (arrays), NO skill.
// Edit/undo/redo warnings carry coverage/holiday_deficit/consecutive/night_hb_gaps
// + skill[]. Every group is optional on the wire; the normalizer fills defaults.
export interface WireWarnings {
  off_counts?: Record<string, number>;
  daikyu_counts?: Record<string, number>;
  coverage?: CoverageWarning[];
  holiday_deficit?: HolidayDeficitWarning[];
  consecutive?: ConsecutiveWarning[];
  night_hb_gaps?: NightHbGap[];
  skill?: SkillWarning[];
}

// The grid sub-object (also returned bare from GET /rosters/{rid}/grid).
export interface WireGrid {
  year: number;
  month: number;
  days_in_month: number;
  weekdays: Record<string, string>; // {"1":"月",...}
  stats_columns: string[]; // 21 labels in order
  holidays: string[]; // ISO dates for 祝 shading
  rows: WireRow[];
  oncall_rows: WireOnCallRow[];
}

// GET /rosters/{rid}: version/status/year/month at top, grid nested, warnings at top.
export interface WireRosterResponse {
  version: number;
  status: string;
  year: number;
  month: number;
  grid: WireGrid;
  warnings: WireWarnings;
}

export interface WireChangedCell {
  staff_id: string;
  date: string; // ISO "2026-06-16"
  text: string;
  category: string; // maps to client `kind` (naming asymmetry vs grid cell_meta.kind)
  locked: boolean;
  fill: string | null; // "#FFFFFF"
  warnings?: unknown[];
}

export interface WireEditResponse {
  edit_id: number;
  seq: number;
  version: number;
  changed_cells: WireChangedCell[];
  stats: Record<string, Record<string, number> | null>; // affected staff only
  warnings: WireWarnings;
  undo_available: boolean;
  redo_available: boolean;
}

// 409 body: FastAPI HTTPException → { detail: { version, grid, warnings } }
// or { detail: { version, reason } } for nothing-to-undo/redo.
export interface WireConflictDetail {
  version: number;
  grid?: WireGrid;
  warnings?: WireWarnings;
  reason?: string;
}
