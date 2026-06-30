// Thin typed client over http.ts for the P3a master API. This is the ONLY place that
// adapts the wire contract (URL shapes, the YYYY/MM↔YYYY-MM key conversion, raw-bytes
// upload) — the editors import these functions and never touch fetch directly.
import { getJson, postJson, putJson, delJson, postRaw } from '../../api/http';
import type {
  CloneResult,
  CommitResult,
  HolidayTarget,
  LocationRow,
  LocationSet,
  MasterSet,
  NightOverrideRow,
  NightQuotaEntry,
  PowerBalanceRow,
  Rank,
  RequestPreview,
  SafetyCheck,
  SkillRow,
  SkillUpdateResult,
  SpecialRuleWire,
  StaffRow,
  TrainingWire,
} from '../types';

/** Convert the display form `YYYY/MM` to the URL-safe path key `YYYY-MM`. */
export const ymToPathKey = (ym: string): string => ym.replace('/', '-');

// --- master sets + clone-before-edit ---------------------------------------
export const listMasterSets = () => getJson<MasterSet[]>('/master-sets');
export const cloneSet = (set: number) => postJson<CloneResult>(`/masters/${set}/clone`, {});

// --- 技師マスタ (staff) ------------------------------------------------------
export const listStaff = (set: number) => getJson<StaffRow[]>(`/masters/${set}/staff`);
export const createStaff = (set: number, row: StaffRow) =>
  postJson<StaffRow>(`/masters/${set}/staff`, row);
export const updateStaff = (set: number, techId: string, row: StaffRow) =>
  putJson<StaffRow>(`/masters/${set}/staff/${techId}`, row);
export const deleteStaff = (set: number, techId: string) =>
  delJson<{ ok: boolean }>(`/masters/${set}/staff/${techId}`);

// --- スキルマスタ (skill) ----------------------------------------------------
export const getSkillMatrix = (set: number) => getJson<SkillRow[]>(`/masters/${set}/skill`);
export const updateSkillCell = (set: number, techId: string, cells: Record<string, Rank>) =>
  putJson<SkillUpdateResult>(`/masters/${set}/skill/${techId}`, cells);

// --- 勤務場所マスタ (location + power_balance, atomic write) ------------------
export const getLocation = (set: number) => getJson<LocationRow[]>(`/masters/${set}/location`);
export const getPowerBalance = (set: number) =>
  getJson<PowerBalanceRow[]>(`/masters/${set}/power_balance`);
export const putLocationSet = (set: number, payload: LocationSet) =>
  putJson<unknown>(`/masters/${set}/location_set`, payload);

// --- 特殊配置ルール (special_rules, whole-array PUT) --------------------------
export const getSpecialRules = (set: number) =>
  getJson<SpecialRuleWire[]>(`/masters/${set}/special_rules`);
export const putSpecialRules = (set: number, rows: SpecialRuleWire[]) =>
  putJson<unknown>(`/masters/${set}/special_rules`, rows);

// --- 業務拡大 (training, whole-array PUT) ------------------------------------
export const getTraining = (set: number) => getJson<TrainingWire[]>(`/masters/${set}/training`);
export const putTraining = (set: number, rows: TrainingWire[]) =>
  putJson<unknown>(`/masters/${set}/training`, rows);

// --- 夜勤回数 (night_quota, month-scoped, whole-array PUT) -------------------
export const getNightQuota = (set: number, ym: string) =>
  getJson<NightQuotaEntry[]>(`/masters/${set}/night_quota?year_month=${ymToPathKey(ym)}`);
export const putNightQuota = (set: number, ym: string, rows: NightQuotaEntry[]) =>
  putJson<unknown>(`/masters/${set}/night_quota?year_month=${ymToPathKey(ym)}`, rows);

// --- 夜勤スキル一覧 (night_overrides, whole-array PUT) -----------------------
export const getNightOverrides = (set: number) =>
  getJson<NightOverrideRow[]>(`/masters/${set}/night_overrides`);
export const putNightOverrides = (set: number, rows: NightOverrideRow[]) =>
  putJson<unknown>(`/masters/${set}/night_overrides`, rows);

// --- 公休数 (holiday_targets, POST upsert, hyphen-key DELETE) ----------------
export const getHolidayTargets = (set: number) =>
  getJson<HolidayTarget[]>(`/masters/${set}/holiday_targets`);
export const upsertHolidayTarget = (set: number, t: HolidayTarget) =>
  postJson<HolidayTarget>(`/masters/${set}/holiday_targets`, t);
export const deleteHolidayTarget = (set: number, ym: string) =>
  delJson<{ ok: boolean }>(`/masters/${set}/holiday_targets/${ymToPathKey(ym)}`);

// --- safety gate ------------------------------------------------------------
export const safetyCheck = (set: number) => getJson<SafetyCheck>(`/masters/${set}/safety-check`);

// --- 予定申請 import (raw CSV bytes as the POST body, NOT multipart) ----------
export const previewRequests = (set: number, body: BodyInit) =>
  postRaw<RequestPreview>(`/masters/requests/preview?master_set_id=${set}`, body);
export const commitRequests = (
  set: number,
  year: number,
  month: number,
  body: BodyInit,
  importedBy: string,
  sourceFilename: string,
) =>
  postRaw<CommitResult>(
    `/masters/requests/${year}/${month}?master_set_id=${set}` +
      `&imported_by=${encodeURIComponent(importedBy)}` +
      `&source_filename=${encodeURIComponent(sourceFilename)}`,
    body,
  );
