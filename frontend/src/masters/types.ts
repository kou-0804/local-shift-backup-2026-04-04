// All master JSON shapes for the P3b master-management UI. Wire shapes mirror the
// SHIPPED P3a backend exactly (byte-fidelity: symbols stored as their literal text,
// ranks as 'A'|'B'|'C'|'D'|'-', tri-state as TRUE/FALSE/'' inherit). `created_at` is
// an ISO-8601 string. year_month has two forms by design: display/validation uses
// `YYYY/MM` (matches the CSV); the night_quota query + holiday DELETE path key use the
// URL-safe `YYYY-MM` — mastersApi.ts is the single place that converts.

export type Rank = 'A' | 'B' | 'C' | 'D' | '-';
export type Tri = 'TRUE' | 'FALSE' | 'inherit';

export type MasterKind =
  | 'staff'
  | 'skill'
  | 'location_set'
  | 'special_rules'
  | 'training'
  | 'night_quota'
  | 'night_overrides'
  | 'holiday_targets'
  | 'requests';

export interface MasterSet {
  master_set_id: number;
  name: string;
  created_at: string;
  parent_set_id: number | null;
}

export interface CloneResult {
  master_set_id: number;
}

export interface StaffRow {
  tech_id: string;
  name: string;
  gender: string; // 男 / 女
  experience_years: number;
  night_ok: string; // ○ / ×
  status: string; // 在籍 / 退職
  note: string;
  oncall_ok: string; // ○ / ×
}

/** GET /masters/{set}/skill → one row per technologist, `cells` keyed by loc code. */
export interface SkillRow {
  tech_id: string;
  name: string;
  cells: Record<string, Rank>;
}

/** PUT /masters/{set}/skill/{tech_id} → result envelope. */
export interface SkillUpdateResult {
  tech_id: string;
  updated: boolean;
  warnings: string[];
}

export interface LocationRow {
  loc_code: string;
  loc_name: string;
  category: string;
  mon: number;
  tue: number;
  wed: number;
  thu: number;
  fri: number;
  sat: number;
  sun: number;
  gender_constraint: string;
  display_order: number;
  active: string; // ○ / ×
}

export interface PowerBalanceRow {
  loc_code: string;
  min_rank: string;
  min_count: number;
  cd_cap: number | null;
  d_solo_ban: string;
}

/** The 勤務場所 file = two different-schema tables. Read as two GETs
 *  (`location`, `power_balance`), written as ONE atomic PUT `/location_set`. */
export interface LocationSet {
  locations: LocationRow[];
  power_balance: PowerBalanceRow[];
}

/** weekday ∈ {月..日, 水金, -}; week ∈ {1..5, -}. */
export interface SpecialRuleWire {
  rule_id: string;
  loc_code: string;
  weekday: string;
  week: string;
  required_count: number;
  rank_cond: string;
  rank_count: number;
  source_loc: string | null;
  source_rank: string | null;
  note: string;
}

export interface TrainingWire {
  modality: string;
  rank_a_only: boolean;
  instructor_ids: string[];
  trainee_ids: string[];
  display_name: string;
}

/** night_quota PUT/GET body row: {name, count, tech_id?} (name is the join key). */
export interface NightQuotaEntry {
  name: string;
  count: number;
  tech_id?: string;
}

/** tri-state on the wire: 'TRUE' | 'FALSE' | '' (blank = inherit from スキルマスタ). */
export interface NightOverrideRow {
  tech_id: string;
  sname: string;
  night_mr: string;
  night_cath: string;
  night_angio: string;
}

export interface HolidayTarget {
  year_month: string; // display form YYYY/MM
  holiday_count: number;
}

export interface SafetyCheck {
  ok: boolean;
  missing: string[];
  load_bearing_ids?: string[];
}

export interface RequestPreviewRow {
  date: string;
  symbol: string;
  raw_rsname: string;
  tech_id_resolved: string | null;
  resolve_status: string;
}

export type RequestLegend = Record<string, string> | { symbol: string; meaning: string }[];

export interface RequestPreview {
  row_count: number;
  rows: RequestPreviewRow[];
  unresolved: string[];
  legend?: RequestLegend;
}

export interface CommitResult {
  import_id: number;
}

/** Advisory (non-blocking) warning surfaced from a mutation response. */
export interface AdvisoryWarning {
  code?: string;
  message: string;
}
