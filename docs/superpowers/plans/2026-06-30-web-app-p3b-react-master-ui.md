# Web App P3b — React Master-Management UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit. Tests focus on **data transforms + validation logic**, not pixel layout.

**Date:** 2026-06-30
**Depends on:** `docs/superpowers/plans/2026-06-29-web-app-p3-master-management.md` (P3a backend — the API contract this UI targets) and the existing `frontend/` app (P2d React roster editor).

**User intent (verbatim, do not dilute):** 「コスト度外視...最高水準で...本番はWindows」 — cost is no object, build to the highest standard, **production runs on Windows**. For this UI that means: zero silent data loss on save, every validation surfaced (never swallowed), the byte-fidelity invariants the backend guards (zero-padded `YYYY/MM`, full-width-space name joins, tri-state inherit) must be **mirrored client-side** so a bad edit is rejected before it ever reaches materialize.

---

## Goal

Build the React master-management section of the web app: a **master-set selector + 9-item master navigation** (the 8 editable masters + the 予定申請 import), **one structured editor per master** matching each master's `web_edit_notes`, **inline validation mirroring the backend validators** (with server 422 errors surfaced clearly), a **clone-before-edit** UX so the seeded "現行" set stays pristine, and a **blocking safety-gate banner** (hardcoded load-bearing staff IDs) that prevents generation when the master set is broken. All data comes from the P3a CRUD + import + safety-check + clone endpoints; **no business logic is re-implemented in JS** beyond input validation (which is intentionally duplicated for fast feedback — the backend remains authoritative).

**Non-goals (P3b):** auth/role-gating of the editors (P5), confirm-lock/archive (P5), Windows Docker packaging (deployment phase), any change to the solver or the 8 hardcoded-logic items in spec §3.5 (those stay in Python and are only *guarded* by the safety gate).

---

## Architecture

```
[ React SPA (existing frontend/) ]
   ?view=masters  ──────────────►  MastersPage (shell)
        │                              ├── MasterSetSelector  (GET /master-sets, POST /masters/{id}/clone)
        │                              ├── MasterNav          (9 tabs: 8 editors + 予定申請 import)
        │                              ├── SafetyGateBanner   (GET /masters/{id}/safety-check)
        │                              └── <one editor>       (per selected master)
        ▼
  frontend/src/masters/api/mastersApi.ts  ── reuses http.ts BASE + getJson/postJson/putJson/delJson/uploadForm
        │  HTTP(JSON) + multipart for 予定申請
        ▼
[ FastAPI P3a router  /masters/... ]   (the contract — see "P3-API contract" below)
```

- **Routing:** the SPA selects the section via the `?view=masters` query param, exactly mirroring how the roster app selects a roster via `?rid=` (`App.tsx`). Default (no `?view`) = roster app (unchanged). `?view=masters` mounts `MastersPage`. Within masters, the selected set + master are also query params (`?view=masters&set=<id>&m=staff`) so a deep link is shareable and a reload restores state.
- **Data layer:** TanStack Query for reads (per-master list queries keyed by `(setId, master)`), `useMutation` for create/update/delete with optimistic cache patch + authoritative merge on success (same pattern as `useEditMutation`). Zustand `mastersStore` holds transient UI state (selected set/master, dirty flag, pending validation banner) — never server data.
- **Clone-before-edit:** the seeded "現行" set is read-only in the UI. The first edit on a pristine set triggers `POST /masters/{id}/clone` → the UI switches `?set=` to the new clone id and re-targets all mutations at it. The pristine set is never mutated (mirrors P3a Task 5 "edit on a copy").
- **Validation:** `frontend/src/masters/validation/validators.ts` mirrors the P3a `validation.py` rules (tech_id `^T\d{3}$`+unique, rank ∈ {A,B,C,D,-}, `YYYY/MM` zero-pad, full-width-space name join, section-B loc-ref, night-quota total==sum, training name resolution, special-rule weekday/week domains). Client validation gives instant feedback and disables Save; the server is still authoritative and any 422 is rendered via `ValidationErrorList`.

---

## Tech Stack

Vite + React 18 + TypeScript (existing). TanStack Query v5, TanStack Table v8, Zustand v5 (all already in `frontend/package.json`). Vitest 2 + @testing-library/react 16 + @testing-library/user-event + jsdom (existing; `src/test/setup.ts` imports `@testing-library/jest-dom/vitest`). API client reuses `frontend/src/api/http.ts` (`VITE_API_BASE` base, `getJson`/`postJson`/`apiUrl`, `ApiError`, `ConflictError`) — **extended additively** with `putJson`, `delJson`, `uploadForm`, and a `ServerValidationError` (422 parser). No new dependencies.

Commands (run from `frontend/`):
- Single test file: `npx vitest run src/masters/<path>.test.ts`
- Whole masters suite: `npx vitest run src/masters`
- Full unit suite: `npm run test`
- Types: `npm run typecheck`

---

## P3-API contract (what P3b assumes the P3a router exposes)

The P3a plan defines per-master CRUD (`GET/POST/PUT/DELETE /masters/{set}/{master}[/{key}]`), `POST /masters/{id}/clone`, `GET /masters/{id}/safety-check → {ok, missing}`, and 予定申請 `POST /masters/requests/preview` + `POST /masters/requests/{year}/{month}`. P3b additionally **assumes** the shapes below. **Items marked ⚠ are not pinned by the P3a plan and MUST be reconciled with the shipped backend** (see the report and Self-Review). Where the backend differs, fix the thin `mastersApi.ts` adapter only — never the editors.

```jsonc
// ⚠ GET /master-sets  → list of bundles (P3a defines per-set masters but not a set-list endpoint)
[{ "id": 1, "name": "現行", "note": "seed", "created_at": "2026-06-30T00:00:00",
   "created_by": "kohei", "parent_set_id": null }]

// POST /masters/{id}/clone  → the new set (parent_set_id = id)
{ "id": 2, "name": "現行 (コピー)", "note": null, "created_at": "2026-06-30T09:00:00",
  "created_by": "kohei", "parent_set_id": 1 }

// GET /masters/{set}/staff  → StaffRow[]
[{ "tech_id":"T001","name":"小川　龍史","gender":"男","experience_years":20,
   "night_ok":"○","status":"在籍","note":"","oncall_ok":"○" }]

// ⚠ GET /masters/{set}/skill  → matrix view (P3a stores long-form ms_skill_cell;
//    PUT is per-tech {loc:rank}; the matrix read shape is assumed)
{ "columns": ["病院MR","CLMR","CT","病CT","ア","心","ク","ポ","精","MG","DR","HB","OP","PICC","入","出","超遅","ク遅","M遅","館山","病L","クL"],
  "rows": [{ "tech_id":"T001","name":"小川　龍史","cells": { "病院MR":"A","CT":"B", "...":"-" } }] }
// PUT /masters/{set}/skill/{tech_id}  body {"病院MR":"C"}  → MutationResult<SkillRow>

// ⚠ GET /masters/{set}/location_set  → the 勤務場所 file as TWO tables (one save)
{ "locations": [{ "loc_code":"病院MR","loc_name":"病院MRI","category":"MR",
    "mon":1,"tue":1,"wed":1,"thu":1,"fri":1,"sat":0,"sun":0,
    "gender_constraint":"なし","display_order":1,"active":"○" }],
  "power_balance": [{ "loc_code":"病院MR","min_rank":"A","min_count":1,"cd_cap":null,"d_solo_ban":"" },
                    { "loc_code":"病院MR","min_rank":"B","min_count":2,"cd_cap":null,"d_solo_ban":"" }] }
// ⚠ PUT /masters/{set}/location_set  body {locations,power_balance} → MutationResult (atomic, one file)

// GET /masters/{set}/special_rules  → SpecialRuleWire[]  (weekday stored as 月..日 | "水金" | "-")
[{ "rule_id":"SR-06","loc_code":"精","weekday":"水金","week":"-","required_count":1,
   "rank_cond":"A","rank_count":1,"source_loc":null,"source_rank":null,"note":"水金A限定" }]

// GET /masters/{set}/training  → TrainingWire[]
[{ "modality":"病院MR","rank_a_only":false,"instructor_ids":["T005"],
   "trainee_ids":["T040","T041"],"display_name":"(MR)" }]

// ⚠ GET /masters/{set}/night_quota?year_month=2026-07  → month-scoped quota
{ "year_month":"2026-07","total":93,"required_on_call":93,
  "entries":[{ "tech_id":"T003","name":"矢野　昌男","count":2 }] }

// GET /masters/{set}/night_overrides  → tri-state per staff
[{ "tech_id":"T010","sname":"石川　和弥","night_mr":"TRUE","night_cath":"FALSE","night_angio":"inherit" }]

// GET /masters/{set}/holiday_targets  → 2-col, year_month in DISPLAY form "YYYY/MM"
[{ "year_month":"2026/04","holiday_count":9 }]
// DELETE key is the ISO-ish path form, e.g. DELETE /masters/{set}/holiday_targets/2027-03

// ⚠ 422 validation error envelope (P3a raises ValidationError(field, JP msg) → assumed shape)
{ "detail": { "field":"年月", "message":"年月はゼロ埋めYYYY/MM形式で入力してください（例 2026/04）" } }

// ⚠ Mutation responses carry advisory warnings (P3a Task 6 attaches night/special warnings to body)
{ "row": { /* updated entity */ }, "warnings": [{ "code":"night_eligibility", "message":"..." }] }

// 予定申請 (multipart upload → preview; then commit)
// POST /masters/requests/preview  (file)  → RequestPreview
{ "row_count": 312, "rows":[{ "date":"2026-07-01","symbol":"☆","raw_rsname":"03 矢野　昌男",
    "tech_id_resolved":"T003","resolve_status":"resolved" }], "unresolved":["99 幽霊"] }
// POST /masters/requests/2026/7  (file)  → { "import_id": 5, "row_count": 312 }
```

---

## File Structure

New package `frontend/src/masters/` (siblings mirror the existing `src/api`, `src/query`, `src/store`, `src/domain` layout):

```
frontend/src/masters/
  types.ts                          # all master JSON shapes (StaffRow, SkillMatrix, LocationSet, ...)
  api/mastersApi.ts                 # typed client over http.ts (list/create/update/delete, clone, safety, requests)
  api/mastersApi.test.ts
  validation/validators.ts          # client mirror of validation.py (pure fns, throw ClientValidationError)
  validation/validators.test.ts
  query/masterKeys.ts               # key factory: masterSetsKey, masterKey(setId, master, scope?)
  query/useMasterData.ts            # useQuery wrappers (useStaff, useSkillMatrix, useLocationSet, ...)
  query/useMasterMutation.ts        # generic create/update/delete mutation w/ optimistic + warnings capture
  store/mastersStore.ts             # zustand: selectedSetId, selectedMaster, pristine flag, dirty, banner
  store/mastersStore.test.ts
  MastersPage.tsx                   # shell: set selector + nav + safety banner + editor switch
  MastersPage.test.tsx
  shell/MasterSetSelector.tsx       # pick set / clone-before-edit
  shell/MasterNav.tsx               # 9 tabs
  shell/SafetyGateBanner.tsx
  shell/SafetyGateBanner.test.tsx
  shell/ValidationErrorList.tsx     # renders server 422 + client errors
  shell/AdvisoryWarnings.tsx        # renders non-blocking warnings[] from mutation responses
  editors/StaffEditor.tsx                 + StaffEditor.test.tsx
  editors/HolidayTargetsEditor.tsx        + HolidayTargetsEditor.test.tsx
  editors/SkillMatrixEditor.tsx           + SkillMatrixEditor.test.tsx
  editors/LocationPowerBalanceEditor.tsx  + LocationPowerBalanceEditor.test.tsx
  editors/SpecialRulesEditor.tsx          + SpecialRulesEditor.test.tsx
  editors/TrainingEditor.tsx              + TrainingEditor.test.tsx
  editors/NightQuotaEditor.tsx            + NightQuotaEditor.test.tsx
  editors/NightSkillEditor.tsx            + NightSkillEditor.test.tsx
  editors/RequestsImport.tsx              + RequestsImport.test.tsx
  editors/transforms/                # pure, heavily-tested data transforms (no React)
    skillMatrix.ts        + skillMatrix.test.ts        # matrix<->per-tech PUT diff; night side-effect detect
    locationPb.ts         + locationPb.test.ts         # validate section-B loc refs; group PB rows by code
    specialRules.ts       + specialRules.test.ts       # 水金 <-> [水,金]; classify rank_cond; week 1-5/every
    nightQuota.ts         + nightQuota.test.ts         # entries<->total; active-staff join
    nightSkill.ts         + nightSkill.test.ts         # tri-state <-> TRUE/FALSE/inherit
  index.ts                          # barrel: export MastersPage
Modify frontend/src/api/http.ts     # add putJson, delJson, uploadForm, ServerValidationError (additive)
Modify frontend/src/App.tsx         # add ?view=masters branch → <MastersPage/>
```

**Order rationale:** API client + types (1) and client validation (2) are the foundation every editor imports. The shell (3) gives a place to mount editors and proves routing + clone + safety-banner wiring. Then simple editors (4 staff, 5 holiday) establish the create/update/delete + validation pattern. Then the three complex editors get focused transform tests (6 skill, 7 location, 8 special-rules). Then the remaining editors (9 training, 10 night-quota, 11 night-skill) and the import (12). The safety gate (13) is wired last because it gates *generation* (a roster-app concern that imports the masters safety check).

---

## Task 1: Master API client + types (extend http.ts)

**Files:** Modify `frontend/src/api/http.ts`; Create `frontend/src/masters/types.ts`, `frontend/src/masters/api/mastersApi.ts`, `frontend/src/masters/query/masterKeys.ts`; Test `frontend/src/masters/api/mastersApi.test.ts`.

- [ ] **Step 1: Write the failing test** (mock `fetch`, assert verbs/paths/bodies + 422 → `ServerValidationError`):

```tsx
// frontend/src/masters/api/mastersApi.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import * as api from './mastersApi';
import { ServerValidationError } from '../../api/http';

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  );
}
afterEach(() => vi.restoreAllMocks());

describe('mastersApi', () => {
  it('lists staff for a set', async () => {
    const f = mockFetch(200, [{ tech_id: 'T001', name: '小川　龍史' }]);
    const rows = await api.listStaff(2);
    expect(f).toHaveBeenCalledWith('/masters/2/staff', undefined);
    expect(rows[0].tech_id).toBe('T001');
  });

  it('clones a set via POST /masters/{id}/clone', async () => {
    mockFetch(200, { id: 3, parent_set_id: 1, name: '現行 (コピー)' });
    const s = await api.cloneSet(1);
    expect(s.parent_set_id).toBe(1);
  });

  it('PUTs a skill cell', async () => {
    const f = mockFetch(200, { row: { tech_id: 'T001' }, warnings: [] });
    await api.updateSkillCell(2, 'T001', { 病院MR: 'C' });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/masters/2/skill/T001');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(init!.body as string)).toEqual({ 病院MR: 'C' });
  });

  it('parses a 422 into ServerValidationError with field + message', async () => {
    mockFetch(422, { detail: { field: '年月', message: 'ゼロ埋めYYYY/MM' } });
    await expect(api.createHolidayTarget(2, { year_month: '2026/4', holiday_count: 9 }))
      .rejects.toBeInstanceOf(ServerValidationError);
  });

  it('safetyCheck returns ok + missing', async () => {
    mockFetch(200, { ok: false, missing: ['T072'] });
    const r = await api.safetyCheck(2);
    expect(r.missing).toContain('T072');
  });

  it('previewRequests posts multipart and returns unresolved', async () => {
    const f = mockFetch(200, { row_count: 1, rows: [], unresolved: ['99 幽霊'] });
    const file = new File(['x'], '予定申請.csv', { type: 'text/csv' });
    const pv = await api.previewRequests(file);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/masters/requests/preview');
    expect(init?.body).toBeInstanceOf(FormData);
    expect(pv.unresolved).toEqual(['99 幽霊']);
  });
});
```

- [ ] **Step 2: Run, verify failure** — `npx vitest run src/masters/api/mastersApi.test.ts` → module-not-found.

- [ ] **Step 3: Extend `http.ts`** (additive — keep existing exports). Add:

```ts
export interface ServerValidationDetail { field?: string; message: string; }
export class ServerValidationError extends Error {
  constructor(public detail: ServerValidationDetail) { super(detail.message); this.name = 'ServerValidationError'; }
}
async function check(res: Response, path: string): Promise<Response> {
  if (res.status === 422) {
    const body = (await readJson(res)) as { detail?: ServerValidationDetail };
    throw new ServerValidationError(body.detail ?? { message: `422 ${path}` });
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res;
}
export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'PUT',
    headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  return (await check(res, path)).json() as Promise<T>;
}
export async function delJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  return (await check(res, path)).json() as Promise<T>;
}
export async function uploadForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form });
  return (await check(res, path)).json() as Promise<T>;
}
```
Also route `postJson`'s non-ok path through `check` so create-endpoints surface 422 as `ServerValidationError` (keep the existing 409 `ConflictError` branch first). `getJson` stays as-is (reads don't 422).

- [ ] **Step 4: Implement `types.ts`** — all shapes from the "P3-API contract" block (StaffRow, `Rank='A'|'B'|'C'|'D'|'-'`, SkillMatrix, LocationRow, PowerBalanceRow, LocationSet, SpecialRuleWire, SpecialRule (UI model w/ `weekdays:string[]`, `week:number|'every'`), TrainingWire/TrainingRule, NightQuota/NightQuotaEntry, `Tri='TRUE'|'FALSE'|'inherit'`, NightOverrideRow, HolidayTarget, MasterSet, SafetyCheck, AdvisoryWarning, `MutationResult<T>={row:T;warnings:AdvisoryWarning[]}`, RequestPreview/RequestPreviewRow). `created_at` is ISO-8601 string.

- [ ] **Step 5: Implement `mastersApi.ts`** — thin typed wrappers. e.g.
```ts
export const listMasterSets = () => getJson<MasterSet[]>('/master-sets');
export const cloneSet = (id: number) => postJson<MasterSet>(`/masters/${id}/clone`, {});
export const listStaff = (set: number) => getJson<StaffRow[]>(`/masters/${set}/staff`);
export const createStaff = (set: number, r: StaffRow) => postJson<MutationResult<StaffRow>>(`/masters/${set}/staff`, r);
export const updateStaff = (set: number, id: string, r: StaffRow) => putJson<MutationResult<StaffRow>>(`/masters/${set}/staff/${id}`, r);
export const deleteStaff = (set: number, id: string) => delJson<{ ok: boolean }>(`/masters/${set}/staff/${id}`);
export const getSkillMatrix = (set: number) => getJson<SkillMatrix>(`/masters/${set}/skill`);
export const updateSkillCell = (set: number, id: string, cells: Record<string, Rank>) => putJson<MutationResult<unknown>>(`/masters/${set}/skill/${id}`, cells);
export const getLocationSet = (set: number) => getJson<LocationSet>(`/masters/${set}/location_set`);
export const putLocationSet = (set: number, s: LocationSet) => putJson<MutationResult<LocationSet>>(`/masters/${set}/location_set`, s);
export const getNightQuota = (set: number, ym: string) => getJson<NightQuota>(`/masters/${set}/night_quota?year_month=${ym}`);
export const safetyCheck = (set: number) => getJson<SafetyCheck>(`/masters/${set}/safety-check`);
export const previewRequests = (file: File) => { const f = new FormData(); f.append('file', file); return uploadForm<RequestPreview>('/masters/requests/preview', f); };
export const commitRequests = (y: number, m: number, file: File) => { const f = new FormData(); f.append('file', file); return uploadForm<{ import_id: number; row_count: number }>(`/masters/requests/${y}/${m}`, f); };
// ...special_rules, training, night_overrides, holiday_targets analogously
```
Implement `masterKeys.ts`: `masterSetsKey = ['master-sets'] as const;` and `masterKey = (set:number, master:string, scope?:string) => ['master', set, master, scope ?? ''] as const;`.

- [ ] **Step 6: Run** `npx vitest run src/masters/api/mastersApi.test.ts` and the existing `npm run test` → all green (proves http.ts change is additive). `npm run typecheck`.

- [ ] **Step 7: Commit** — `feat(p3b-ui): master API client + types + http verbs (put/del/upload, 422 parser)`

---

## Task 2: Client-side validators (mirror validation.py)

**Files:** Create `frontend/src/masters/validation/validators.ts`; Test `frontend/src/masters/validation/validators.test.ts`.

Pure functions, no React. They give instant feedback and gate Save; the server stays authoritative. Mirror P3a `validation.py` exactly.

- [ ] **Step 1: Write the failing test** (one assertion per rule from spec §9 / P3a Task 5):

```ts
// frontend/src/masters/validation/validators.test.ts
import { describe, it, expect } from 'vitest';
import * as v from './validators';

describe('master validators', () => {
  it('tech_id must be Tnnn', () => {
    expect(v.isTechId('T001')).toBe(true);
    expect(v.isTechId('X1')).toBe(false);
    expect(v.isTechId('T01')).toBe(false);
  });
  it('tech_id unique within set', () => {
    expect(() => v.assertTechIdUnique(new Set(['T001']), 'T001')).toThrow(v.ClientValidationError);
  });
  it('skill rank domain {A,B,C,D,-}', () => {
    ['A','B','C','D','-'].forEach((r) => expect(v.isRank(r)).toBe(true));
    expect(v.isRank('E')).toBe(false);
  });
  it('year_month must be zero-padded YYYY/MM (the #1 footgun)', () => {
    expect(v.isYearMonth('2026/04')).toBe(true);
    expect(v.isYearMonth('2026/4')).toBe(false);   // silent loader miss in Python
    expect(v.isYearMonth('2026/13')).toBe(false);
  });
  it('full-width-space name must join (half-width space will not)', () => {
    const known = new Set(['石川　和弥']);          // U+3000
    expect(() => v.assertNameJoins('石川 和弥', known)).toThrow(v.ClientValidationError);
    expect(v.assertNameJoins('石川　和弥', known)).toBeUndefined();
  });
  it('section-B power-balance code must reference a section-A location', () => {
    expect(() => v.assertPbLocationRef('存在しない', new Set(['病院MR','CT']))).toThrow();
  });
  it('night-quota declared total must equal sum of entries', () => {
    expect(() => v.assertNightTotal([{ count: 2 }, { count: 1 }], 4)).toThrow();
    expect(v.assertNightTotal([{ count: 2 }, { count: 1 }], 3)).toBeUndefined();
  });
  it('training names must resolve to staff ids', () => {
    expect(() => v.assertTrainingResolves(['T999'], new Set(['T001']))).toThrow();
  });
  it('special-rule weekday and week domains', () => {
    expect(v.isWeekdayToken('水金')).toBe(true);
    expect(v.isWeekdayToken('Z')).toBe(false);
    expect(v.isWeekToken('every')).toBe(true);
    expect(v.isWeekToken(6)).toBe(false);
  });
  it('flags unenforced special-rule string conditions', () => {
    expect(v.isUnenforcedRankCond('D同士禁止')).toBe(true);
    expect(v.isUnenforcedRankCond('A')).toBe(false);
  });
});
```

- [ ] **Step 2: Run, verify failure** → module-not-found.

- [ ] **Step 3: Implement `validators.ts`.** `class ClientValidationError extends Error { constructor(public field: string, message: string) { super(message); } }`. Predicates return booleans; `assert*` throw `ClientValidationError` with a JP message matching the backend wording (so client and server errors read consistently). Rules: `isTechId = /^T\d{3}$/`; `isRank ∈ {A,B,C,D,-}`; `isGender ∈ {男,女}`; `isOX ∈ {○,×}`; `isStatus ∈ {在籍,退職}`; `isYearMonth = /^\d{4}\/(0[1-9]|1[0-2])$/`; `isWeekdayToken ∈ {月,火,水,木,金,土,日,水金,-}`; `isWeekToken ∈ {1,2,3,4,5,'every'}` (or `-`); `UNENFORCED_RANK_CONDS = ['D同士禁止','CD上限','CD単独禁止']`. `assertNameJoins(name, known)` normalizes nothing — it requires an exact membership in `known` (the join key is byte-sensitive; the backend only normalizes 　↔space as a *fallback*, so the UI warns on the half-width form rather than silently relying on the fallback).

- [ ] **Step 4: Run** `npx vitest run src/masters/validation` → green. `npm run typecheck`.

- [ ] **Step 5: Commit** — `feat(p3b-ui): client validators mirroring backend (tech_id, rank, YYYY/MM, name-join, pb-ref, night-total)`

---

## Task 3: Master-set selector + nav shell + clone-before-edit + routing

**Files:** Create `frontend/src/masters/store/mastersStore.ts`, `frontend/src/masters/query/useMasterData.ts`, `frontend/src/masters/query/useMasterMutation.ts`, `frontend/src/masters/MastersPage.tsx`, `frontend/src/masters/shell/MasterSetSelector.tsx`, `frontend/src/masters/shell/MasterNav.tsx`, `frontend/src/masters/shell/ValidationErrorList.tsx`, `frontend/src/masters/shell/AdvisoryWarnings.tsx`, `frontend/src/masters/index.ts`; Modify `frontend/src/App.tsx`; Test `frontend/src/masters/store/mastersStore.test.ts`, `frontend/src/masters/MastersPage.test.tsx`.

- [ ] **Step 1: Store test (write first)**:

```ts
// frontend/src/masters/store/mastersStore.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useMastersStore } from './mastersStore';

beforeEach(() => useMastersStore.getState().reset());

describe('mastersStore', () => {
  it('selects set + master', () => {
    useMastersStore.getState().selectSet(1, true /* pristine */);
    useMastersStore.getState().selectMaster('staff');
    const s = useMastersStore.getState();
    expect(s.selectedSetId).toBe(1);
    expect(s.selectedMaster).toBe('staff');
    expect(s.pristine).toBe(true);
  });
  it('clone re-targets the set and clears pristine', () => {
    useMastersStore.getState().selectSet(1, true);
    useMastersStore.getState().onCloned({ id: 2, parent_set_id: 1 } as any);
    expect(useMastersStore.getState().selectedSetId).toBe(2);
    expect(useMastersStore.getState().pristine).toBe(false);
  });
  it('tracks dirty', () => {
    useMastersStore.getState().markDirty();
    expect(useMastersStore.getState().dirty).toBe(true);
  });
});
```

- [ ] **Step 2: Run, verify failure**.

- [ ] **Step 3: Implement `mastersStore.ts`** (Zustand, same shape as `uiStore.ts`): `selectedSetId:number|null`, `selectedMaster:MasterKind` (`'staff'|'skill'|'location_set'|'special_rules'|'training'|'night_quota'|'night_overrides'|'holiday_targets'|'requests'`), `pristine:boolean`, `dirty:boolean`, actions `selectSet(id,pristine)`, `selectMaster(m)`, `onCloned(set)` (sets `selectedSetId=set.id; pristine=false`), `markDirty()`, `clearDirty()`, `reset()`.

- [ ] **Step 4: Implement `useMasterData.ts` + `useMasterMutation.ts`.**
  - `useMasterData`: thin `useQuery` wrappers — `useMasterSets()`, `useStaff(set)`, `useSkillMatrix(set)`, `useLocationSet(set)`, `useSpecialRules(set)`, `useTraining(set)`, `useNightQuota(set, ym)`, `useNightOverrides(set)`, `useHolidayTargets(set)`, each keyed via `masterKey`.
  - `useMasterMutation`: a generic hook returning `{ save, remove, isPending, warnings, serverError }`. On a write it (a) optionally fires `cloneSet` first when `pristine` (clone-before-edit), re-targeting via `onCloned`, (b) calls the mutation, (c) on success invalidates `masterKey(set,master)` and stashes `result.warnings` for `AdvisoryWarnings`, (d) on `ServerValidationError` stashes `{field,message}` for `ValidationErrorList` (do NOT throw to an error boundary). Mirror the optimistic+authoritative shape of `useEditMutation`.

- [ ] **Step 5: Shell test (write first)** — mock the API, assert the shell renders the set selector, the 9 nav tabs, and switches the mounted editor:

```tsx
// frontend/src/masters/MastersPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MastersPage } from './MastersPage';
import * as api from './api/mastersApi';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MastersPage /></QueryClientProvider>);
}

describe('MastersPage shell', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('lists sets and shows the 9 master tabs', async () => {
    vi.spyOn(api, 'listMasterSets').mockResolvedValue([
      { id: 1, name: '現行', note: null, created_at: '2026-06-30T00:00:00', created_by: 'k', parent_set_id: null },
    ]);
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    vi.spyOn(api, 'listStaff').mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByRole('option', { name: /現行/ })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: '技師マスタ' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '予定申請' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(9);
  });
  it('switches editor when a tab is clicked', async () => {
    vi.spyOn(api, 'listMasterSets').mockResolvedValue([
      { id: 1, name: '現行', note: null, created_at: '2026-06-30T00:00:00', created_by: 'k', parent_set_id: null },
    ]);
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    vi.spyOn(api, 'getHolidayTargets').mockResolvedValue([{ year_month: '2026/04', holiday_count: 9 }]);
    vi.spyOn(api, 'listStaff').mockResolvedValue([]);
    renderPage();
    await screen.findByRole('tab', { name: '公休数' });
    await userEvent.click(screen.getByRole('tab', { name: '公休数' }));
    await waitFor(() => expect(screen.getByText('2026/04')).toBeInTheDocument());
  });
});
```

- [ ] **Step 6: Implement the shell.**
  - `MasterNav.tsx`: a `role="tablist"` of 9 `role="tab"` buttons: 技師マスタ→`staff`, スキルマスタ→`skill`, 勤務場所マスタ→`location_set`, 特殊配置ルール→`special_rules`, 業務拡大→`training`, 夜勤回数→`night_quota`, 夜勤スキル一覧→`night_overrides`, 公休数→`holiday_targets`, 予定申請→`requests`. Click → `selectMaster` + write `?m=` to the URL.
  - `MasterSetSelector.tsx`: `<select>` from `useMasterSets()`, plus a "編集用に複製" button that calls `cloneSet` (also auto-triggered on first edit). Pristine "現行" rows render a 読み取り専用 badge.
  - `MastersPage.tsx`: reads `?set=` / `?m=` from `window.location.search` (same `URLSearchParams` approach as `App.tsx`), seeds the store, renders `<MasterSetSelector/> <SafetyGateBanner set={...}/> <MasterNav/>` then switches on `selectedMaster` to the editor (lazy import OK). Editors not yet built render a placeholder until their task lands.
  - `ValidationErrorList.tsx`: renders `{field, message}` (server) + client errors as an alert list. `AdvisoryWarnings.tsx`: renders `warnings[]` as dismissible non-blocking notices.
  - `index.ts`: `export { MastersPage } from './MastersPage';`

- [ ] **Step 7: Wire routing in `App.tsx`** — additive branch:
```tsx
const view = new URLSearchParams(window.location.search).get('view');
if (view === 'masters') return <MastersPage />;
```
(keep the existing `?rid=` roster path as the default).

- [ ] **Step 8: Run** `npx vitest run src/masters` and `npm run test` → green. `npm run typecheck`.

- [ ] **Step 9: Commit** — `feat(p3b-ui): masters shell — set selector, 9-tab nav, clone-before-edit, ?view=masters routing`

---

## Task 4: 技師マスタ — StaffEditor (flat editable grid)

**Files:** Create `frontend/src/masters/editors/StaffEditor.tsx`; Test `frontend/src/masters/editors/StaffEditor.test.tsx`.

`web_edit_notes`: flat one-row-per-person grid. Fields: text 技師ID (unique + Tnnn), text 氏名 (cross-file join key — warn on rename), select 性別 {男,女}, int 経験年数, toggle 夜勤可否 ○/× (store the symbol), select 在籍状況 {在籍,退職}, free-text 備考, toggle 拘束可否 ○/×. 退職 does NOT auto-exclude — surface that.

- [ ] **Step 1: Write the failing test** (TanStack-Table grid via RTL; assert validation gating + cross-file rename warning + 退職 notice):

```tsx
// frontend/src/masters/editors/StaffEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StaffEditor } from './StaffEditor';
import * as api from '../api/mastersApi';

const ROW = { tech_id: 'T001', name: '小川　龍史', gender: '男', experience_years: 20,
  night_ok: '○', status: '在籍', note: '', oncall_ok: '○' } as const;

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><StaffEditor setId={2} /></QueryClientProvider>);
}

describe('StaffEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders imported rows', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as any]);
    renderEditor();
    await waitFor(() => expect(screen.getByDisplayValue('T001')).toBeInTheDocument());
  });
  it('blocks save on a non-Tnnn id and shows an inline error', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as any]);
    const create = vi.spyOn(api, 'createStaff');
    renderEditor();
    await screen.findByDisplayValue('T001');
    await userEvent.click(screen.getByTestId('staff-add'));
    await userEvent.type(screen.getByTestId('staff-id-new'), 'X1');
    await userEvent.click(screen.getByTestId('staff-save-new'));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText(/Tnnn/)).toBeInTheDocument();
  });
  it('warns that renaming 氏名 breaks cross-file joins', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as any]);
    renderEditor();
    await screen.findByDisplayValue('小川　龍史');
    await userEvent.clear(screen.getByTestId('staff-name-T001'));
    await userEvent.type(screen.getByTestId('staff-name-T001'), '小川　竜史');
    expect(screen.getByText(/結合キー/)).toBeInTheDocument();
  });
  it('surfaces that 退職 does not auto-exclude from scheduling', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([{ ...ROW, status: '退職' } as any]);
    renderEditor();
    await waitFor(() => expect(screen.getByText(/自動的に除外されません/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run, verify failure**.

- [ ] **Step 3: Implement `StaffEditor.tsx`** — TanStack Table with editable cells. Per-cell validation uses Task-2 validators (`isTechId`, uniqueness against the loaded set, `isGender`, `isOX`, `isStatus`, `experience_years ≥ 0`). Save buttons disabled while a row has a client error; on click call `createStaff`/`updateStaff` via `useMasterMutation` (clone-before-edit fires automatically when pristine). Render a dirty-row 氏名 rename warning (`結合キー` note) and a banner when any row is 退職 (`自動的に除外されません`). Surface `ServerValidationError` via `ValidationErrorList` and `warnings[]` via `AdvisoryWarnings`. Use stable `data-testid`s (`staff-id-new`, `staff-name-T001`, ...).

- [ ] **Step 4: Run** `npx vitest run src/masters/editors/StaffEditor.test.tsx` → green. `npm run typecheck`.

- [ ] **Step 5: Commit** — `feat(p3b-ui): 技師マスタ StaffEditor (flat grid, Tnnn+unique, rename + 退職 warnings)`

---

## Task 5: 公休数 — HolidayTargetsEditor (2-col table, zero-padded YYYY/MM)

**Files:** Create `frontend/src/masters/editors/HolidayTargetsEditor.tsx`; Test `frontend/src/masters/editors/HolidayTargetsEditor.test.tsx`.

`web_edit_notes`: simplest 2-col key/value table; **reject single-digit month** (the #1 silent footgun — Python does exact `df['年月']==f'{year}/{month:02d}'`). Enforce 年月 uniqueness; sane 公休数 bounds (~7..11). Pre-seed the 12 fiscal-year months so users only fill numbers.

- [ ] **Step 1: Write the failing test**:

```tsx
// frontend/src/masters/editors/HolidayTargetsEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HolidayTargetsEditor } from './HolidayTargetsEditor';
import * as api from '../api/mastersApi';

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><HolidayTargetsEditor setId={2} /></QueryClientProvider>);
}

describe('HolidayTargetsEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders the 2-col table', async () => {
    vi.spyOn(api, 'getHolidayTargets').mockResolvedValue([{ year_month: '2026/04', holiday_count: 9 }]);
    renderEditor();
    await waitFor(() => expect(screen.getByDisplayValue('2026/04')).toBeInTheDocument());
  });
  it('rejects an un-padded month before calling the API', async () => {
    vi.spyOn(api, 'getHolidayTargets').mockResolvedValue([]);
    const create = vi.spyOn(api, 'createHolidayTarget');
    renderEditor();
    await screen.findByTestId('ht-add');
    await userEvent.click(screen.getByTestId('ht-add'));
    await userEvent.type(screen.getByTestId('ht-ym-new'), '2026/4');
    await userEvent.type(screen.getByTestId('ht-count-new'), '9');
    await userEvent.click(screen.getByTestId('ht-save-new'));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText(/ゼロ埋め/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement** — 2-col editable list using `isYearMonth` + uniqueness + bounds; pre-seed missing fiscal-year months as empty-count rows; create/update/delete via `useMasterMutation`.
- [ ] **Step 4: Run** `npx vitest run src/masters/editors/HolidayTargetsEditor.test.tsx` → green. `npm run typecheck`.
- [ ] **Step 5: Commit** — `feat(p3b-ui): 公休数 HolidayTargetsEditor (2-col, zero-padded YYYY/MM guard)`

---

## Task 6 (COMPLEX): スキルマスタ — SkillMatrixEditor (constrained {A,B,C,D,-} matrix)

**Files:** Create `frontend/src/masters/editors/transforms/skillMatrix.ts`, `frontend/src/masters/editors/SkillMatrixEditor.tsx`; Test `frontend/src/masters/editors/transforms/skillMatrix.test.ts`, `frontend/src/masters/editors/SkillMatrixEditor.test.tsx`.

`web_edit_notes`: grid rows=技師 (label 氏名, key 技師ID), columns=22 skill codes, each cell a **constrained dropdown {A,B,C,D,-}** (no free text — non-ABCD silently becomes NONE in Python). Exclude 技師ID/氏名 from the editable rank grid. **Surface the hidden side effect**: 病院MR/CLMR/ア/心/HB ranks ≥B feed night-shift eligibility.

- [ ] **Step 1: Transform test (write first)** — the genuinely testable logic is the cell-edit → PUT diff and the night side-effect detector:

```ts
// frontend/src/masters/editors/transforms/skillMatrix.test.ts
import { describe, it, expect } from 'vitest';
import { cellEditPayload, nightEligibilityChange, NIGHT_LOCS } from './skillMatrix';

describe('skillMatrix transforms', () => {
  it('builds a per-tech PUT body containing only the changed cell', () => {
    expect(cellEditPayload('病院MR', 'C')).toEqual({ 病院MR: 'C' });
  });
  it('detects a night-eligibility loss when an MR rank drops below B', () => {
    expect(nightEligibilityChange('病院MR', 'A', 'C')).toBe('lost');   // >=B -> <B
    expect(nightEligibilityChange('病院MR', 'C', 'B')).toBe('gained'); // <B -> >=B
    expect(nightEligibilityChange('病院MR', 'A', 'B')).toBe('none');   // stays >=B
  });
  it('only the 5 night-relevant locations trigger the side effect', () => {
    expect(NIGHT_LOCS).toEqual(['病院MR', 'CLMR', 'ア', '心', 'HB']);
    expect(nightEligibilityChange('CT', 'A', '-')).toBe('none');
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `skillMatrix.ts`** — `cellEditPayload(loc, rank) => ({ [loc]: rank })`; `NIGHT_LOCS = ['病院MR','CLMR','ア','心','HB']`; `rankAtLeastB(r) = r === 'A' || r === 'B'`; `nightEligibilityChange(loc, oldR, newR)`: if `loc ∉ NIGHT_LOCS` → `'none'`; else compare `rankAtLeastB` old vs new → `'lost'|'gained'|'none'` (matches `data_loader.py:33-47` ≥B derivation).
- [ ] **Step 4: Editor test (write first)** — assert non-ABCD is impossible (dropdown, not text) and that a downgrade shows the night warning:

```tsx
// frontend/src/masters/editors/SkillMatrixEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SkillMatrixEditor } from './SkillMatrixEditor';
import * as api from '../api/mastersApi';

const MATRIX = { columns: ['病院MR', 'CT'],
  rows: [{ tech_id: 'T001', name: '小川　龍史', cells: { 病院MR: 'A', CT: 'B' } }] };

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><SkillMatrixEditor setId={2} /></QueryClientProvider>);
}

describe('SkillMatrixEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders cells as {A,B,C,D,-} selects (no free text)', async () => {
    vi.spyOn(api, 'getSkillMatrix').mockResolvedValue(MATRIX as any);
    renderEditor();
    const sel = await screen.findByTestId('skill-T001-病院MR') as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(['A', 'B', 'C', 'D', '-']);
  });
  it('warns about night-eligibility loss when 病院MR drops below B', async () => {
    vi.spyOn(api, 'getSkillMatrix').mockResolvedValue(MATRIX as any);
    vi.spyOn(api, 'updateSkillCell').mockResolvedValue({ row: {}, warnings: [] } as any);
    renderEditor();
    const sel = await screen.findByTestId('skill-T001-病院MR');
    await userEvent.selectOptions(sel, 'C');
    await waitFor(() => expect(screen.getByText(/夜勤/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 5: Implement `SkillMatrixEditor.tsx`** — TanStack Table; first two columns (技師ID/氏名) read-only; every rank cell a `<select>` of `['A','B','C','D','-']` with `data-testid={`skill-${techId}-${loc}`}`. On change call `updateSkillCell(set, techId, cellEditPayload(loc, rank))`; if `nightEligibilityChange(...)!=='none'` show an inline JP night-eligibility notice (in addition to any server `warnings[]`). Column add/remove (= new schedulable location) is **out of scope** here — render columns read-only structurally and note admin-only column management as future work.
- [ ] **Step 6: Run** `npx vitest run src/masters/editors/SkillMatrixEditor.test.tsx src/masters/editors/transforms/skillMatrix.test.ts` → green. `npm run typecheck`.
- [ ] **Step 7: Commit** — `feat(p3b-ui): スキルマスタ SkillMatrixEditor (constrained {A,B,C,D,-} grid + night side-effect)`

---

## Task 7 (COMPLEX): 勤務場所マスタ — LocationPowerBalanceEditor (TWO sub-editors → one save)

**Files:** Create `frontend/src/masters/editors/transforms/locationPb.ts`, `frontend/src/masters/editors/LocationPowerBalanceEditor.tsx`; Test `frontend/src/masters/editors/transforms/locationPb.test.ts`, `frontend/src/masters/editors/LocationPowerBalanceEditor.test.tsx`.

`web_edit_notes`: ONE physical file = TWO different-schema tables. Present as two sub-editors but persist as **one save** (`PUT /location_set`). Section A: per-location row with 7 weekday headcount ints (Mon..Sun), code (unique), name, category, 性別制約 select, 表示順 int, 有効 ○/×. Section B: a child grid filtered by 場所コード (multiple rank rows per location allowed — additive), rank select, min-count/CD-cap ints, D単独禁止 toggle. **Validate every section-B 場所コード references an existing section-A location.** Warn that toggling 有効=× removes a location and that section-B rows referencing it become dead.

- [ ] **Step 1: Transform test (write first)**:

```ts
// frontend/src/masters/editors/transforms/locationPb.test.ts
import { describe, it, expect } from 'vitest';
import { validateLocationSet, groupPbByCode, deadPbRows } from './locationPb';

const SET = {
  locations: [
    { loc_code: '病院MR', loc_name: 'MRI', category: 'MR', mon: 1, tue: 1, wed: 1, thu: 1, fri: 1, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 1, active: '○' },
    { loc_code: 'PICC', loc_name: 'PICC', category: 'x', mon: 0, tue: 0, wed: 0, thu: 0, fri: 0, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 2, active: '×' },
  ],
  power_balance: [
    { loc_code: '病院MR', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' },
    { loc_code: '病院MR', min_rank: 'B', min_count: 2, cd_cap: null, d_solo_ban: '' },
    { loc_code: 'PICC', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' },
  ],
} as any;

describe('locationPb transforms', () => {
  it('groups additive PB rows by code (病院MR appears twice)', () => {
    expect(groupPbByCode(SET.power_balance).get('病院MR')).toHaveLength(2);
  });
  it('rejects a PB row whose code has no section-A location', () => {
    const bad = { ...SET, power_balance: [...SET.power_balance, { loc_code: '幽霊', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' }] };
    expect(() => validateLocationSet(bad)).toThrow(/幽霊/);
  });
  it('rejects a duplicate section-A code', () => {
    const dup = { ...SET, locations: [...SET.locations, SET.locations[0]] };
    expect(() => validateLocationSet(dup)).toThrow();
  });
  it('flags PB rows pointing at an inactive (有効=×) location as dead', () => {
    expect(deadPbRows(SET).map((r: any) => r.loc_code)).toEqual(['PICC']);
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `locationPb.ts`** — `groupPbByCode(rows) => Map<code, rows[]>`; `validateLocationSet({locations,power_balance})` throws `ClientValidationError` on a duplicate section-A `loc_code` or any section-B `loc_code` not in the section-A set (uses `assertPbLocationRef`); `deadPbRows(set)` returns PB rows whose location has `active==='×'`.
- [ ] **Step 4: Editor test (write first)** — assert the two sub-grids render, the active toggle warns, an orphan PB code blocks save:

```tsx
// frontend/src/masters/editors/LocationPowerBalanceEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocationPowerBalanceEditor } from './LocationPowerBalanceEditor';
import * as api from '../api/mastersApi';

const SET = {
  locations: [{ loc_code: '病院MR', loc_name: 'MRI', category: 'MR', mon: 1, tue: 1, wed: 1, thu: 1, fri: 1, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 1, active: '○' }],
  power_balance: [{ loc_code: '病院MR', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' }],
};

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><LocationPowerBalanceEditor setId={2} /></QueryClientProvider>);
}

describe('LocationPowerBalanceEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders both sub-editors from one location_set', async () => {
    vi.spyOn(api, 'getLocationSet').mockResolvedValue(SET as any);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('loc-grid')).toBeInTheDocument());
    expect(screen.getByTestId('pb-grid')).toBeInTheDocument();
  });
  it('saves both tables in ONE PUT /location_set', async () => {
    vi.spyOn(api, 'getLocationSet').mockResolvedValue(SET as any);
    const put = vi.spyOn(api, 'putLocationSet').mockResolvedValue({ row: SET, warnings: [] } as any);
    renderEditor();
    await screen.findByTestId('loc-grid');
    await userEvent.click(screen.getByTestId('locset-save'));
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][1]).toMatchObject({ locations: expect.any(Array), power_balance: expect.any(Array) });
  });
  it('warns when toggling 有効 to ×', async () => {
    vi.spyOn(api, 'getLocationSet').mockResolvedValue(SET as any);
    renderEditor();
    await userEvent.click(await screen.findByTestId('loc-active-病院MR'));
    expect(screen.getByText(/スケジュール対象から外れます/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Implement `LocationPowerBalanceEditor.tsx`** — two TanStack Tables (`loc-grid`, `pb-grid`) sharing one in-memory `LocationSet`. The PB grid is grouped by `loc_code` (via `groupPbByCode`) with "add rank row" per location. A single `locset-save` runs `validateLocationSet` then `putLocationSet(set, draft)` (one atomic call). Toggling 有効=× shows the `スケジュール対象から外れます` warning + lists any now-dead PB rows (`deadPbRows`). Section-B 場所コード inputs are dropdowns sourced from section-A codes (can't type an orphan). Surface server `warnings[]`/422 as usual.
- [ ] **Step 6: Run** `npx vitest run src/masters/editors/LocationPowerBalanceEditor.test.tsx src/masters/editors/transforms/locationPb.test.ts` → green. `npm run typecheck`.
- [ ] **Step 7: Commit** — `feat(p3b-ui): 勤務場所マスタ LocationPowerBalanceEditor (two sub-editors, one atomic save, loc-ref validation)`

---

## Task 8 (COMPLEX): 特殊配置ルール — SpecialRulesEditor (structured form)

**Files:** Create `frontend/src/masters/editors/transforms/specialRules.ts`, `frontend/src/masters/editors/SpecialRulesEditor.tsx`; Test `frontend/src/masters/editors/transforms/specialRules.test.ts`, `frontend/src/masters/editors/SpecialRulesEditor.test.tsx`.

`web_edit_notes`: most logic-dense. Structured form (not raw text): 場所コード dropdown; 対象曜日 as a **weekday multi-select that models 水金 as selecting Wed+Fri** (not a magic token); 対象週 as 1-5 or 'every'; ランク条件 as a dropdown distinguishing the numeric rank-floor case (A/B/C/D + count) from the special string conditions. **CRITICAL UI warning: 'D同士禁止' / 'CD上限' / 'CD単独禁止' parse to NONE and are NOT enforced** (dead branch). Cross-location sourcing (選出元場所+選出元ランク) is an optional paired sub-form. Keep 凡例 legend out of the editable grid.

- [ ] **Step 1: Transform test (write first)** — the 水金 expand/collapse + rank-cond classification is the core logic:

```ts
// frontend/src/masters/editors/transforms/specialRules.test.ts
import { describe, it, expect } from 'vitest';
import { weekdaysFromToken, tokenFromWeekdays, classifyRankCond, weekFromToken, tokenFromWeek } from './specialRules';

describe('specialRules transforms', () => {
  it('expands 水金 to [水, 金] and back', () => {
    expect(weekdaysFromToken('水金')).toEqual(['水', '金']);
    expect(tokenFromWeekdays(['水', '金'])).toBe('水金');
  });
  it('maps a single weekday and the all-days token', () => {
    expect(weekdaysFromToken('月')).toEqual(['月']);
    expect(weekdaysFromToken('-')).toEqual([]);          // all days
    expect(tokenFromWeekdays([])).toBe('-');
  });
  it('round-trips 対象週 1-5 and every', () => {
    expect(weekFromToken('-')).toBe('every');
    expect(weekFromToken('3')).toBe(3);
    expect(tokenFromWeek('every')).toBe('-');
    expect(tokenFromWeek(3)).toBe('3');
  });
  it('classifies rank conditions (numeric floor vs unenforced string)', () => {
    expect(classifyRankCond('A')).toBe('rank_floor');
    expect(classifyRankCond('D同士禁止')).toBe('unenforced');
    expect(classifyRankCond('-')).toBe('none');
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `specialRules.ts`** — `weekdaysFromToken('水金') => ['水','金']`, single `'月'..'日' => [it]`, `'-' => []`; `tokenFromWeekdays([水,金]) => '水金'`, `[]=>'-'`, single => that day, any other multi-set => join (or reject — note: the loader only special-cases 水金; arbitrary multi-day combos aren't representable, so the UI should restrict multi-select to either a single day, the all-days option, or the 水金 pair, and `tokenFromWeekdays` throws `ClientValidationError` on an unsupported combo). `weekFromToken`/`tokenFromWeek` for 1-5/every. `classifyRankCond(c) => 'rank_floor' | 'unenforced' | 'none'` using `UNENFORCED_RANK_CONDS`.
- [ ] **Step 4: Editor test (write first)** — assert the unenforced warning appears and that saving a 水金 rule serializes to the `水金` token:

```tsx
// frontend/src/masters/editors/SpecialRulesEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SpecialRulesEditor } from './SpecialRulesEditor';
import * as api from '../api/mastersApi';

const RULES = [{ rule_id: 'SR-06', loc_code: '精', weekday: '水金', week: '-', required_count: 1,
  rank_cond: 'A', rank_count: 1, source_loc: null, source_rank: null, note: '' }];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><SpecialRulesEditor setId={2} /></QueryClientProvider>);
}

describe('SpecialRulesEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('shows 水金 as Wed+Fri selected', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue(RULES as any);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('sr-wd-水')).toBeChecked());
    expect(screen.getByTestId('sr-wd-金')).toBeChecked();
  });
  it('warns that string rank conditions are not enforced', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue(
      [{ ...RULES[0], rank_cond: 'D同士禁止' }] as any);
    renderEditor();
    await waitFor(() => expect(screen.getByText(/未適用|未実装/)).toBeInTheDocument());
  });
  it('serializes Wed+Fri back to the 水金 token on save', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue(RULES as any);
    const upd = vi.spyOn(api, 'updateSpecialRule').mockResolvedValue({ row: {}, warnings: [] } as any);
    renderEditor();
    await screen.findByTestId('sr-save-SR-06');
    await userEvent.click(screen.getByTestId('sr-save-SR-06'));
    expect(upd.mock.calls[0][2]).toMatchObject({ weekday: '水金' });
  });
});
```

- [ ] **Step 5: Implement `SpecialRulesEditor.tsx`** — structured per-rule form: 場所コード dropdown (from location_set codes), weekday checkboxes (model 水金 via `tokenFromWeekdays`), week select (1-5/every), required-count int, rank-cond dropdown that branches `rank_floor` (show rank + count) vs `unenforced` (show a prominent `この条件はスケジューラで未適用です` warning) vs `none`; optional 選出元場所/選出元ランク paired sub-form. On save, map the UI model back to the wire (`weekday` token via `tokenFromWeekdays`, `week` via `tokenFromWeek`) and call `updateSpecialRule`/`createSpecialRule`. Never render the 凡例 legend rows (backend keeps them in `format_json` and round-trips them; they are not editable here).
- [ ] **Step 6: Run** `npx vitest run src/masters/editors/SpecialRulesEditor.test.tsx src/masters/editors/transforms/specialRules.test.ts` → green. `npm run typecheck`.
- [ ] **Step 7: Commit** — `feat(p3b-ui): 特殊配置ルール SpecialRulesEditor (structured form, 水金 model, unenforced-condition warning)`

---

## Task 9: 業務拡大 — TrainingEditor (multi-select pickers + ランクA toggle)

**Files:** Create `frontend/src/masters/editors/TrainingEditor.tsx`; Test `frontend/src/masters/editors/TrainingEditor.test.tsx`.

`web_edit_notes`: instructors/trainees as **multi-select pickers backed by the staff list** (store stable IDs, not fuzzy free-text — avoids the substring mis-match landmine). Explicit **'any rank-A holder' toggle** that emits the `ランクA保持者` sentinel. 対象モダリティ dropdown (location/skill codes). 表示名 free text. Warn when a typed name fails to resolve.

- [ ] **Step 1: Write the failing test**:

```tsx
// frontend/src/masters/editors/TrainingEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TrainingEditor } from './TrainingEditor';
import * as api from '../api/mastersApi';

const TRAIN = [{ modality: '病院MR', rank_a_only: false, instructor_ids: ['T005'],
  trainee_ids: ['T040'], display_name: '(MR)' }];
const STAFF = [{ tech_id: 'T005', name: '指導　太郎' }, { tech_id: 'T040', name: '育成　花子' }];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><TrainingEditor setId={2} /></QueryClientProvider>);
}

describe('TrainingEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders staff names from stable ids', async () => {
    vi.spyOn(api, 'getTraining').mockResolvedValue(TRAIN as any);
    vi.spyOn(api, 'listStaff').mockResolvedValue(STAFF as any);
    renderEditor();
    await waitFor(() => expect(screen.getByText('指導　太郎')).toBeInTheDocument());
  });
  it('rank-A toggle replaces the instructor picker and emits the sentinel', async () => {
    vi.spyOn(api, 'getTraining').mockResolvedValue(TRAIN as any);
    vi.spyOn(api, 'listStaff').mockResolvedValue(STAFF as any);
    const upd = vi.spyOn(api, 'updateTraining').mockResolvedValue({ row: {}, warnings: [] } as any);
    renderEditor();
    await userEvent.click(await screen.findByTestId('train-rankA-病院MR'));
    await userEvent.click(screen.getByTestId('train-save-病院MR'));
    expect(upd.mock.calls[0][2]).toMatchObject({ rank_a_only: true, instructor_ids: [] });
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `TrainingEditor.tsx`** — per-rule card: 対象モダリティ dropdown, instructor multi-select (disabled when rank-A toggle on; payload `instructor_ids:[]` + `rank_a_only:true`), trainee multi-select (both backed by `listStaff`, value=tech_id, label=name), 表示名 text. Validate trainees/instructors resolve via `assertTrainingResolves`. Save via `updateTraining`/`createTraining`.
- [ ] **Step 4: Run** `npx vitest run src/masters/editors/TrainingEditor.test.tsx` → green. `npm run typecheck`.
- [ ] **Step 5: Commit** — `feat(p3b-ui): 業務拡大 TrainingEditor (ID-backed multi-select + ランクA保持者 toggle)`

---

## Task 10: 夜勤回数 — NightQuotaEditor (month picker + per-staff numeric, total==sum)

**Files:** Create `frontend/src/masters/editors/transforms/nightQuota.ts`, `frontend/src/masters/editors/NightQuotaEditor.tsx`; Test `frontend/src/masters/editors/transforms/nightQuota.test.ts`, `frontend/src/masters/editors/NightQuotaEditor.test.tsx`.

`web_edit_notes`: do NOT expose the raw CSV. Pick a target month → one numeric field per ACTIVE technologist (join 名前 vs 技師マスタ, hide 退職). The **column-header month is authoritative**. Validate 合計 == sum; warn if 合計 != 必要当直者数.

- [ ] **Step 1: Transform test (write first)**:

```ts
// frontend/src/masters/editors/transforms/nightQuota.test.ts
import { describe, it, expect } from 'vitest';
import { sumCounts, reconcile } from './nightQuota';

describe('nightQuota transforms', () => {
  it('sums entry counts', () => {
    expect(sumCounts([{ count: 2 }, { count: 1 }] as any)).toBe(3);
  });
  it('reconciles declared total vs sum and vs required_on_call', () => {
    expect(reconcile([{ count: 2 }, { count: 1 }] as any, 3, 3)).toEqual({ totalOk: true, requiredMismatch: false });
    expect(reconcile([{ count: 2 }] as any, 3, 4)).toEqual({ totalOk: false, requiredMismatch: true });
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `nightQuota.ts`** — `sumCounts(entries)`, `reconcile(entries, total, requiredOnCall) => { totalOk: sum===total, requiredMismatch: total!==requiredOnCall }`.
- [ ] **Step 4: Editor test (write first)** — month picker drives the query; save is blocked when total != sum:

```tsx
// frontend/src/masters/editors/NightQuotaEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NightQuotaEditor } from './NightQuotaEditor';
import * as api from '../api/mastersApi';

const Q = { year_month: '2026-07', total: 3, required_on_call: 3,
  entries: [{ tech_id: 'T003', name: '矢野　昌男', count: 2 }, { tech_id: 'T004', name: '田中　一', count: 1 }] };

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><NightQuotaEditor setId={2} /></QueryClientProvider>);
}

describe('NightQuotaEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('shows one numeric field per active staff for the picked month', async () => {
    vi.spyOn(api, 'getNightQuota').mockResolvedValue(Q as any);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('nq-count-T003')).toHaveValue(2));
  });
  it('blocks save when the running total drifts from the declared total', async () => {
    vi.spyOn(api, 'getNightQuota').mockResolvedValue(Q as any);
    const save = vi.spyOn(api, 'putNightQuota');
    renderEditor();
    const f = await screen.findByTestId('nq-count-T003');
    await userEvent.clear(f);
    await userEvent.type(f, '5');                       // sum 6 != declared 3
    await userEvent.click(screen.getByTestId('nq-save'));
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByText(/合計/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Implement `NightQuotaEditor.tsx`** — a month `<select>`/picker that sets the `year_month` query param and re-queries `getNightQuota`. A numeric field per entry (`nq-count-{tech_id}`). A live 合計 display recomputed via `sumCounts`; the editor auto-syncs the declared total to the sum (the loader treats the column as authoritative) but surfaces `reconcile(...).requiredMismatch` as a warning. Save via `putNightQuota(set, ym, draft)`; block while `!totalOk` if the UI lets total be edited independently.
- [ ] **Step 6: Run** `npx vitest run src/masters/editors/NightQuotaEditor.test.tsx src/masters/editors/transforms/nightQuota.test.ts` → green. `npm run typecheck`.
- [ ] **Step 7: Commit** — `feat(p3b-ui): 夜勤回数 NightQuotaEditor (month picker + per-staff numeric, total==sum guard)`

---

## Task 11: 夜勤スキル一覧 — NightSkillEditor (tri-state TRUE/FALSE/inherit)

**Files:** Create `frontend/src/masters/editors/transforms/nightSkill.ts`, `frontend/src/masters/editors/NightSkillEditor.tsx`; Test `frontend/src/masters/editors/transforms/nightSkill.test.ts`, `frontend/src/masters/editors/NightSkillEditor.test.tsx`.

`web_edit_notes`: per-staff toggle grid, key by 技師ID, three **tri-state** controls (TRUE / FALSE / inherit-from-skill-master) for MR, Cardiac-Cath, Angio. Make 'blank = inherit' explicit. No night-HB override path here (HB comes only from スキルマスタ).

- [ ] **Step 1: Transform test (write first)** — the tri-state <-> wire mapping:

```ts
// frontend/src/masters/editors/transforms/nightSkill.test.ts
import { describe, it, expect } from 'vitest';
import { triToWire, wireToTri } from './nightSkill';

describe('nightSkill tri-state', () => {
  it('maps inherit to null (blank) on the wire', () => {
    expect(triToWire('inherit')).toBeNull();
    expect(triToWire('TRUE')).toBe('TRUE');
    expect(triToWire('FALSE')).toBe('FALSE');
  });
  it('maps a blank/unknown wire value back to inherit', () => {
    expect(wireToTri(null)).toBe('inherit');
    expect(wireToTri('')).toBe('inherit');
    expect(wireToTri('TRUE')).toBe('TRUE');
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `nightSkill.ts`** — `triToWire('inherit')=>null` else the literal `'TRUE'|'FALSE'`; `wireToTri(v)=> v==='TRUE'||v==='FALSE' ? v : 'inherit'` (blank/`null`/unknown => inherit, matching the loader's "only exact TRUE/FALSE take effect").
- [ ] **Step 4: Editor test (write first)** — three tri-state controls per staff, inherit visibly distinct from FALSE:

```tsx
// frontend/src/masters/editors/NightSkillEditor.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NightSkillEditor } from './NightSkillEditor';
import * as api from '../api/mastersApi';

const ROWS = [{ tech_id: 'T010', sname: '石川　和弥', night_mr: 'TRUE', night_cath: 'FALSE', night_angio: 'inherit' }];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><NightSkillEditor setId={2} /></QueryClientProvider>);
}

describe('NightSkillEditor', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders three tri-state selects with inherit distinct from FALSE', async () => {
    vi.spyOn(api, 'getNightOverrides').mockResolvedValue(ROWS as any);
    renderEditor();
    const mr = await screen.findByTestId('ns-mr-T010') as HTMLSelectElement;
    expect(mr.value).toBe('TRUE');
    expect((screen.getByTestId('ns-angio-T010') as HTMLSelectElement).value).toBe('inherit');
    expect([...mr.options].map((o) => o.value)).toEqual(['TRUE', 'FALSE', 'inherit']);
  });
  it('sends inherit as a blank override on save', async () => {
    vi.spyOn(api, 'getNightOverrides').mockResolvedValue(ROWS as any);
    const upd = vi.spyOn(api, 'updateNightOverride').mockResolvedValue({ row: {}, warnings: [] } as any);
    renderEditor();
    await userEvent.selectOptions(await screen.findByTestId('ns-mr-T010'), 'inherit');
    await userEvent.click(screen.getByTestId('ns-save-T010'));
    expect(upd.mock.calls[0][2]).toMatchObject({ night_mr: null });
  });
});
```

- [ ] **Step 5: Implement `NightSkillEditor.tsx`** — TanStack Table keyed by 技師ID; three `<select>` of `['TRUE','FALSE','inherit']` per row (`ns-mr-`, `ns-cath-`, `ns-angio-`). On save map via `triToWire`. Render a one-line note that HB night-eligibility has no override path here.
- [ ] **Step 6: Run** `npx vitest run src/masters/editors/NightSkillEditor.test.tsx src/masters/editors/transforms/nightSkill.test.ts` → green. `npm run typecheck`.
- [ ] **Step 7: Commit** — `feat(p3b-ui): 夜勤スキル一覧 NightSkillEditor (tri-state TRUE/FALSE/inherit)`

---

## Task 12: 予定申請 — RequestsImport (upload → preview unresolved → import)

**Files:** Create `frontend/src/masters/editors/RequestsImport.tsx`; Test `frontend/src/masters/editors/RequestsImport.test.tsx`.

`web_edit_notes`: IMPORT ONLY — no CRUD. Upload CSV → validation/preview (skip leading blanks + `Sample Data`; report unresolved RSName) → commit per-month (`予定申請_YYYYMM.csv`). Show a HolidaySymbol legend.

- [ ] **Step 1: Write the failing test**:

```tsx
// frontend/src/masters/editors/RequestsImport.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RequestsImport } from './RequestsImport';
import * as api from '../api/mastersApi';

function renderImport() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><RequestsImport setId={2} /></QueryClientProvider>);
}

describe('RequestsImport', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('uploads, previews, and reports unresolved RSName before commit', async () => {
    vi.spyOn(api, 'previewRequests').mockResolvedValue({ row_count: 2,
      rows: [{ date: '2026-07-01', symbol: '☆', raw_rsname: '03 矢野　昌男', tech_id_resolved: 'T003', resolve_status: 'resolved' }],
      unresolved: ['99 幽霊'] } as any);
    renderImport();
    const file = new File(['x'], '予定申請.csv', { type: 'text/csv' });
    await userEvent.upload(screen.getByTestId('req-file'), file);
    await waitFor(() => expect(screen.getByText(/99 幽霊/)).toBeInTheDocument());
    expect(screen.getByText(/未解決/)).toBeInTheDocument();
  });
  it('commits to the picked year/month after preview', async () => {
    vi.spyOn(api, 'previewRequests').mockResolvedValue({ row_count: 1, rows: [], unresolved: [] } as any);
    const commit = vi.spyOn(api, 'commitRequests').mockResolvedValue({ import_id: 5, row_count: 1 } as any);
    renderImport();
    await userEvent.upload(screen.getByTestId('req-file'), new File(['x'], '予定申請.csv'));
    await screen.findByTestId('req-commit');
    await userEvent.click(screen.getByTestId('req-commit'));
    expect(commit).toHaveBeenCalled();   // (year, month, file)
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `RequestsImport.tsx`** — file input (`req-file`) → `previewRequests(file)` → render a preview table + an `未解決RSName` callout (`unresolved[]`) + a HolidaySymbol legend (holiday vs forced-work vs 夜希 vs 17休/17業). A year/month picker + `req-commit` button → `commitRequests(year, month, file)`. No editing of rows (Power Apps is the system of record). Disable commit until a preview succeeds.
- [ ] **Step 4: Run** `npx vitest run src/masters/editors/RequestsImport.test.tsx` → green. `npm run typecheck`.
- [ ] **Step 5: Commit** — `feat(p3b-ui): 予定申請 RequestsImport (upload/preview/unresolved-report/commit, month-suffixed)`

---

## Task 13: Safety-gate banner + block generation

**Files:** Create `frontend/src/masters/shell/SafetyGateBanner.tsx`; Test `frontend/src/masters/shell/SafetyGateBanner.test.tsx`. (Wire the same check into the roster app's generate action.)

`web_edit_notes` / spec §9: before generation, verify the code-fixed staff IDs (T001/T013/T025/T072/T002/T022/T006/T023) exist; if missing, a **clear blocking banner** must prevent generation. Backend `GET /masters/{set}/safety-check → {ok, missing}`.

- [ ] **Step 1: Write the failing test**:

```tsx
// frontend/src/masters/shell/SafetyGateBanner.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafetyGateBanner } from './SafetyGateBanner';
import * as api from '../api/mastersApi';

function renderBanner(onChange?: (ok: boolean) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><SafetyGateBanner setId={2} onResult={onChange} /></QueryClientProvider>);
}

describe('SafetyGateBanner', () => {
  beforeEach(() => vi.restoreAllMocks());
  it('renders nothing blocking when the gate passes', async () => {
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    const cb = vi.fn();
    renderBanner(cb);
    await waitFor(() => expect(cb).toHaveBeenCalledWith(true));
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('shows a blocking alert naming every missing id', async () => {
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: false, missing: ['T072', 'T013'] });
    const cb = vi.fn();
    renderBanner(cb);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText(/T072/)).toBeInTheDocument();
    expect(screen.getByText(/T013/)).toBeInTheDocument();
    expect(cb).toHaveBeenCalledWith(false);
  });
});
```

- [ ] **Step 2: Run, verify failure**.
- [ ] **Step 3: Implement `SafetyGateBanner.tsx`** — `useQuery` on `safetyCheck(setId)`. When `!ok`, render `role="alert"` with the JP message `生成不可: コード固定の技師ID {missing} が技師マスタに存在しません（§3.5 参照）` listing every missing id. Call `onResult(ok)` so the parent (and the roster generate action) can disable the 生成 button. Mount it in `MastersPage` (top of shell) and also expose it / its query for the roster app's generate flow so a broken master set blocks generation there too (the backend worker raises `SafetyError`, but blocking client-side avoids a guaranteed-failed job).
- [ ] **Step 4: Run** `npx vitest run src/masters/shell/SafetyGateBanner.test.tsx` → green. `npm run typecheck`.
- [ ] **Step 5: Commit** — `feat(p3b-ui): load-bearing-ID safety-gate banner blocks generation`

---

## Final verification

- [ ] `cd frontend && npm run test` → entire suite green (masters + existing roster tests; proves the http.ts change is additive).
- [ ] `cd frontend && npm run typecheck` → no TS errors.
- [ ] `cd frontend && npm run build` → `tsc --noEmit && vite build` succeeds.
- [ ] Manual smoke (optional, needs the P3a API running): open `/?view=masters`, confirm the set selector lists "現行", clicking a master tab loads its editor, an invalid edit shows an inline error and the disabled Save, and deleting a load-bearing staff id flips the SafetyGateBanner to blocking.

---

## Self-Review

**Spec coverage (§9 / §3.4 / web_edit_notes):**
- Master-set selector + 9-item nav (8 editors + 予定申請) → Task 3. ✅
- 技師マスタ flat grid (Tnnn+unique, ○/×, 退職 not auto-excluded, rename warning) → Task 4. ✅
- スキルマスタ constrained {A,B,C,D,-} matrix + night ≥B side-effect → Task 6. ✅
- 勤務場所マスタ TWO sub-editors → one atomic save + section-B loc-ref + 有効=× dead-row warning → Task 7. ✅
- 特殊配置ルール structured form, 水金=Wed+Fri, unenforced D同士禁止/CD上限/CD単独禁止 warning → Task 8. ✅
- 業務拡大 ID-backed multi-select + ランクA保持者 toggle → Task 9. ✅
- 夜勤回数 month picker + per-active-staff numeric + total==sum → Task 10. ✅
- 夜勤スキル一覧 tri-state TRUE/FALSE/inherit (blank=inherit) → Task 11. ✅
- 公休数 2-col zero-padded YYYY/MM → Task 5. ✅
- 予定申請 import-only upload/preview/unresolved/commit → Task 12. ✅
- Inline validation mirroring backend + server 422 surfaced → Task 2 + `ValidationErrorList`. ✅
- Safety-gate blocking banner → Task 13. ✅
- Clone-before-edit (pristine "現行" never mutated) → Task 3 store + `useMasterMutation`. ✅

**Placeholder scan:** No `...` in shipped code; the `...`/`as any` in test bodies are illustrative fixtures the implementer fills. Editors not yet built render an explicit placeholder in `MastersPage` until their task lands (intentional, removed as tasks complete). No TODO left at the end of the sequence.

**Type consistency:** Symbols stored as their literal text (`○`/`×`, `'TRUE'|'FALSE'|'inherit'` tri-state, ranks `'A'|'B'|'C'|'D'|'-'`) — never coerced to boolean client-side, matching the byte-level master tables. `created_at` is ISO-8601 string. `year_month` exists in two forms by design: **display/validation = `YYYY/MM`** (zero-padded, matches the CSV), **path key for night_quota/holiday delete = `YYYY-MM`** (URL-safe) — the adapter in `mastersApi.ts` is the single place that converts, so editors only ever see the display form. All wire shapes live in `types.ts`; components import normalized types, never raw `fetch` JSON.

**Determinism / no-logic-duplication:** the UI re-implements only *input validation* (for fast feedback); it does NOT re-implement any solver/derivation logic. The backend remains authoritative (server 422 always wins; advisory `warnings[]` always render). Night-eligibility and unenforced-condition notices are *advisory mirrors* of the backend's own warnings, not independent enforcement.

**Windows (本番はWindows):** This is a browser SPA — no filesystem newline/encoding concerns live here; the byte-fidelity invariants are the backend's (P3a). The UI's contribution to Windows safety is *prevention*: the zero-padded `YYYY/MM` guard (Task 5), the full-width-space name-join guard (Task 2/4), and the tri-state inherit mapping (Task 11) stop the exact edits that would otherwise produce a master set the byte-exact materialize can't round-trip cleanly.

**P3-API assumptions that MUST be reconciled with the shipped P3a backend** (fix `mastersApi.ts`/`types.ts` only, never the editors):
1. ⚠ `GET /master-sets` (set-list endpoint) — P3a defines per-set masters and `clone`, but not an explicit list-of-sets endpoint. The shell needs one.
2. ⚠ `GET /masters/{set}/skill` returning a **matrix view** `{columns, rows[].cells}` — P3a stores long-form `ms_skill_cell` and only specifies the per-tech `PUT`. Confirm a matrix read exists (or add a thin assembler client-side from a long-form read).
3. ⚠ `GET/PUT /masters/{set}/location_set` as a **single combined 勤務場所 payload** (atomic two-table save) — P3a exposes `location` and `power_balance` as separate masters. If no combined endpoint ships, the editor's one Save must call both endpoints in sequence and the plan's "one atomic PUT" test changes to "two ordered PUTs" (prefer adding the combined endpoint to preserve atomicity/byte-order).
4. ⚠ 422 envelope `{ detail: { field, message } }` — confirm the backend's custom `ValidationError` handler shape (vs FastAPI's default `{detail:[{loc,msg,...}]}`); `ServerValidationError` parsing in `http.ts` depends on it.
5. ⚠ Mutation responses carry `{ row, warnings: AdvisoryWarning[] }` — confirm the advisory-warning attachment shape from P3a Task 6 (night-eligibility / unenforced-condition).
6. ⚠ `GET /masters/{set}/night_quota?year_month=...` month-scoping + a `PUT` that regenerates the title/header/footer server-side — confirm the read/write contract (the editor must not have to reconstruct the title/footer).
7. ⚠ `holiday_targets`/`night_quota` path keys use `YYYY-MM` while the body/display uses `YYYY/MM` — confirm the exact key format the backend routes on.

---

## Next (out of scope for P3b)

- **P5 — auth / confirm-lock / monthly archive (spec §10):** role-gate the editors (admin can edit masters; editor/viewer cannot), disable Save/clone for non-admins, and surface the confirm-lock state. The masters section should be hidden from `viewer`.
- **Confirm-before-destructive UX:** a confirm dialog for delete + for clone-discard of unsaved edits (reuse the existing `ConflictDialog` pattern). A "dirty edits will be lost" guard on tab/set switch.
- **Admin-only schema changes:** adding/removing a スキル column (= a new schedulable location) and the matching 勤務場所 row — validated against the location master (spec §15 open question). Out of P3b on purpose.
- **Windows deployment (spec §13):** the SPA ships in the `web` container of the Docker Compose; confirm `VITE_API_BASE` points at the `api` service and that the masters routes work behind the LAN-only reverse proxy.
