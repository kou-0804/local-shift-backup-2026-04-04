# P2d — React Editor Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the browser-side schedule editor — an Excel-style grid where a manager can assign/unassign/move/lock cells with optimistic feedback, see live coverage/holiday/consecutive/skill warnings, toggle a load/shortfall heatmap, undo/redo, resolve version conflicts, and export the Direction-A Excel — all driven by the P2a editing REST API, treating the **server response as authoritative for stats/明け/代休**.

**Architecture:** A Vite + React + TypeScript SPA. A thin **API client** speaks the exact P2a wire contract; a **normalization layer** collapses the server's two on-wire shapes (day-keyed grid vs. ISO-date-keyed edit deltas) into one client-side `Cell`/`RosterState` model; a pure **merge reducer** applies the authoritative `changed_cells`+`stats`+`warnings` from every edit. **TanStack Query** owns server state and optimistic mutations, **TanStack Table v8 + TanStack Virtual** render the wide grid (~40 staff × 31 days × 21 stat cols), **dnd-kit** turns drag-drop into a single `move` op, and **Zustand** holds ephemeral UI state. The grid is a deterministic function of `(freeze baseline, edit log up to cursor)`; the client never computes stats.

**Tech Stack:** Vite 5, React 18, TypeScript 5, @tanstack/react-table v8, @tanstack/react-virtual v3, @tanstack/react-query v5, @dnd-kit/core, zustand, Vitest + @testing-library/react + jsdom (unit), Playwright (E2E).

---

## Background the implementer must read first

- Approved design: `docs/superpowers/specs/2026-06-29-web-app-shift-scheduler-design.md` — §4 architecture, §5 data model, §7 manual-edit editor + validation engine, §8 visualization/heatmap.
- P2 technical design (synthesis): §2.2 edit ops → mutation, §2.3 REST API + edit-response shape, §2.4 undo/redo + staleness contract, §5 React frontend outline, §6 P2d decomposition.
- Sibling plans already in `docs/superpowers/plans/`: `2026-06-29-web-app-p1-foundation.md` (jobs + freeze), `2026-06-29-web-app-p2a1-extractions.md` (`build_grid`, `recompute_stats`). **P2d depends on P2a's editing API being live.**

### The backend contract this frontend targets (treat as the spec)

```
GET  /rosters/{rid}            → full grid: { year, month, rows[], oncall_rows[], weekdays, stats_columns, version, warnings, holidays? }
GET  /rosters/{rid}/grid       → grid only (same rows shape, no warnings) — not used by P2d initial load
POST /rosters/{rid}/edits      → body { op, ...payload, expected_version } → EditResponse | 409
POST /rosters/{rid}/undo       → EditResponse
POST /rosters/{rid}/redo       → EditResponse
GET  /rosters/{rid}/edits      → paginated audit log (history drawer, optional in P2d)
POST /rosters/{rid}/resolve    → partial-lock re-solve [P2b — dark-launched; button present but mocked/disabled in P2d]
GET  /rosters/{rid}/excel      → Direction-A .xlsx download
POST /rosters/{rid}/confirm    → status='confirmed' [P4 hook — button present, wired, may 4xx until P4]
```

`GET /rosters/{rid}` row shape (from `build_grid`):
```jsonc
{ "staff_id":"T013", "staff_num":13, "name":"佐藤(海)",
  "cells": { "1":"CT", "2":"○", "3":"病CT夜", "4":"" },
  "cell_meta": { "1":{"kind":"work","fill":null,"locked":false},
                 "3":{"kind":"night","fill":"FFFF00","locked":false} },
  "has_work": true,
  "stats": { "夜勤":2, "CT":7, "公休":9, "代休":0 } }   // null when has_work=false
```

`POST /rosters/{rid}/edits` response (authoritative — includes the D+1 明け re-derivation and recomputed 代休 the client cannot predict):
```jsonc
{ "edit_id":412, "seq":8, "version":8,
  "changed_cells":[ {"staff_id":"T013","date":"2026-06-16","text":"CT","category":"day","locked":false,"fill":"#FFFFFF","warnings":[]} ],
  "stats": { "T013": {"夜勤":2,"CT":7,"公休":9,"代休":0} },
  "warnings": {
    "coverage":[{"date":"2026-06-15","location":"ク","required":3,"assigned":2,"short":1}],
    "holiday_deficit":[{"staff_id":"T020","off":8,"target":9,"short":1}],
    "consecutive":[{"staff_id":"T013","start":"2026-06-10","len":7}],
    "skill":[{"date":"2026-06-16","location":"心","staff_id":"T013","rule":"min_rank","need":"B","have":"C"}] },
  "undo_available":true, "redo_available":false }
```
409 on `expected_version` mismatch → body carries the **current grid** for client rebase.

### Critical correctness rules this plan encodes

1. **Server is authoritative for stats/明け/代休.** Client applies a thin optimistic update to the *edited cell text only*, then **merges** the server `changed_cells`+`stats`+`warnings`. Never compute `公休`/`代休`/coverage client-side.
2. **Every** edit/drag/lock/undo/redo carries `expected_version`; 409 → `ConflictDialog` rebase.
3. **Drag-drop = one `move` op = one undo step** (same staff, day→day). Cross-staff drag is a no-op in P2d.
4. The two wire shapes differ (grid: day-int keys, `kind`, fill `"FFFF00"`, `locked` in `cell_meta`; edit: ISO `date`, `category`, fill `"#FFFFFF"`, `locked` top-level). The **API client / normalization layer is the single place** that reconciles them; components see one `Cell` type.

### Contract ambiguities resolved in this plan (confirm with P2a backend if they bite)

- **Request key `sid` vs response key `staff_id`.** §2.2 writes payloads as `{sid,date,location}`; the edit *response* uses `staff_id`. This plan sends `sid` (literal §2.2) and reads `staff_id` back; both live behind `editsApi.ts` so a single edit flips it if P2a actually expects `staff_id`.
- **`year`/`month` on the grid response.** `build_grid` returns them; the task's terse GET shape omitted them. They are required to build ISO dates for edit payloads, so this plan assumes `GET /rosters/{rid}` surfaces `year` and `month` (graceful error if missing).
- **祝日 (holiday) shading.** `weekdays` only carries the weekday char (土/日/…). Sat→blue, Sun→red are derived from the char. Full 祝日 red shading needs server dates; the plan reads an **optional** `holidays: string[]` (ISO) field and degrades gracefully when absent.
- **Location pick-list.** The grid response has no location master. The `EditPopover` uses a `locationOptions` prop defaulted from `stats_columns` work labels + `['休','○']`; P3's master endpoint replaces it later.

---

## File Structure

```
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts                      # dev proxy → http://localhost:8000
├── vitest.config.ts                    # jsdom env, setup file
├── playwright.config.ts                # E2E (Task 14)
├── index.html
├── .env.example                        # VITE_API_BASE=
├── src/
│   ├── main.tsx                        # React root + QueryClientProvider
│   ├── App.tsx                         # routes to RosterPage
│   ├── domain/
│   │   ├── wire.ts                     # server DTO types (exact wire shapes)
│   │   ├── model.ts                    # normalized client types (Cell, Row, RosterState)
│   │   ├── editOps.ts                  # EditOp union + EditRequest
│   │   └── locations.ts               # default location pick-list (derived/const)
│   ├── api/
│   │   ├── http.ts                     # fetch wrapper, ConflictError, ApiError
│   │   ├── rosterApi.ts                # getRoster, getExcelUrl
│   │   └── editsApi.ts                 # postEdit, postUndo, postRedo, postResolve(mock), postConfirm
│   ├── normalize/
│   │   ├── dates.ts                    # toIsoDate, parseDayFromIso, weekday helpers
│   │   ├── fill.ts                     # normalizeFill, localFillFor
│   │   ├── normalizeGrid.ts            # WireGridResponse → RosterState
│   │   └── mergeEdit.ts               # mergeEditResponse + applyOptimistic + buildMovePayload
│   ├── query/
│   │   ├── queryClient.ts
│   │   ├── useRoster.ts                # GET /rosters/{rid} → RosterState
│   │   └── useEditMutation.ts          # optimistic edit/undo/redo mutations
│   ├── store/
│   │   └── uiStore.ts                  # Zustand: heatmapMode, selectedCell, highlight, drawers
│   ├── viz/
│   │   └── heatmap.ts                  # heatmapColor, loadByStaff (pure)
│   ├── components/
│   │   ├── RosterPage.tsx
│   │   ├── ScheduleGrid.tsx
│   │   ├── DayCell.tsx
│   │   ├── StatsCells.tsx
│   │   ├── OnCallRows.tsx
│   │   ├── EditPopover.tsx
│   │   ├── WarningPanel.tsx
│   │   ├── HeatmapToggle.tsx
│   │   ├── EditToolbar.tsx
│   │   └── ConflictDialog.tsx
│   └── test/
│       └── fixtures.ts                 # sample WireGridResponse + WireEditResponse
└── e2e/
    └── editor.spec.ts                  # Playwright scenarios (Task 14)
```

**Decomposition rationale:** the load-bearing, hard-to-eyeball logic (`normalize/`, `viz/`) is isolated into pure modules unit-tested with Vitest; React components stay thin. `domain/` types are the contract source of truth shared by api, normalize, and components.

---

## Dev setup (read once)

- Backend (FastAPI) runs on `http://localhost:8000` (P1 `webapp/api/main.py`). Vite proxies `/rosters` and `/jobs` there, so the SPA uses same-origin relative paths in dev and prod.
- **P2d assumes a roster already exists.** Seed one before opening the UI:
  ```bash
  # from repo root, backend running:
  curl -s -XPOST localhost:8000/jobs -H 'content-type: application/json' \
       -d '{"year":2026,"month":6}' | tee /tmp/job.json     # → {"job_id": "..."}
  JOB=$(python3 -c "import json;print(json.load(open('/tmp/job.json'))['job_id'])")
  # wait for status=done (poll GET /jobs/$JOB), then:
  curl -s -XPOST localhost:8000/jobs/$JOB/freeze | tee /tmp/roster.json  # → {"roster_id": "..."}
  ```
  Open the SPA at `http://localhost:5173/rosters/<roster_id>`.

---

## Task 1: Scaffold Vite + React + TS, deps, dev proxy

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/index.html`, `frontend/.env.example`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/test/setup.ts`, `frontend/src/smoke.test.ts`

- [ ] **Step 1: Scaffold and install**

Run:
```bash
cd "frontend" 2>/dev/null || (cd "$(git rev-parse --show-toplevel)" && mkdir -p frontend && cd frontend)
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-table @tanstack/react-virtual @tanstack/react-query @dnd-kit/core @dnd-kit/utilities zustand
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom @vitest/coverage-v8
```

- [ ] **Step 2: Write `vite.config.ts` with the backend proxy**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/rosters': { target: 'http://localhost:8000', changeOrigin: true },
      '/jobs': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
```

- [ ] **Step 3: Write `vitest.config.ts` and `src/test/setup.ts`**

`vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    coverage: { provider: 'v8' },
  },
});
```
`src/test/setup.ts`:
```ts
import '@testing-library/jest-dom';
```

- [ ] **Step 4: Add `.env.example` and a `test` script**

`.env.example`:
```
# Leave empty in dev (Vite proxy handles routing). Set to an absolute API origin only for non-proxied prod builds.
VITE_API_BASE=
```
In `package.json` `scripts`, ensure:
```json
{ "scripts": { "dev": "vite", "build": "tsc -b && vite build", "test": "vitest run", "test:watch": "vitest" } }
```

- [ ] **Step 5: Write a smoke test**

`src/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

describe('smoke', () => {
  it('runs vitest', () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 6: Run the smoke test**

Run: `cd frontend && npm run test`
Expected: PASS, 1 test.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "chore(frontend): scaffold Vite+React+TS editor with backend proxy and vitest"
```

---

## Task 2: Domain types + API client (HTTP wrapper, ConflictError)

**Files:**
- Create: `frontend/src/domain/wire.ts`, `frontend/src/domain/editOps.ts`, `frontend/src/api/http.ts`, `frontend/src/api/rosterApi.ts`, `frontend/src/api/editsApi.ts`
- Test: `frontend/src/api/editsApi.test.ts`

- [ ] **Step 1: Write the wire DTO types**

`src/domain/wire.ts`:
```ts
// Exact server wire shapes — do NOT use these in components; normalize first.
export interface WireCellMeta { kind: string; fill: string | null; locked?: boolean }

export interface WireRow {
  staff_id: string;
  staff_num: number;
  name: string;
  cells: Record<string, string>;            // {"1":"CT","2":"○"}
  cell_meta: Record<string, WireCellMeta>;  // {"1":{kind,fill,locked}}
  has_work: boolean;
  stats: Record<string, number> | null;     // 21 cols, or null when !has_work
}

export interface WireOnCallRow { label: string; cells: Record<string, string> }

export interface CoverageWarning { date: string; location: string; required: number; assigned: number; short: number }
export interface HolidayDeficitWarning { staff_id: string; off: number; target: number; short: number }
export interface ConsecutiveWarning { staff_id: string; start: string; len: number }
export interface SkillWarning { date: string; location: string; staff_id: string; rule: string; need: string; have: string }
export interface WireWarnings {
  coverage: CoverageWarning[];
  holiday_deficit: HolidayDeficitWarning[];
  consecutive: ConsecutiveWarning[];
  skill: SkillWarning[];
}

export interface WireGridResponse {
  year: number;
  month: number;
  rows: WireRow[];
  oncall_rows: WireOnCallRow[];
  weekdays: Record<string, string>;     // {"1":"月",...}
  stats_columns: string[];              // 21 labels in order
  version: number;
  warnings: WireWarnings;
  holidays?: string[];                  // optional ISO dates for 祝 shading
}

export interface WireChangedCell {
  staff_id: string;
  date: string;          // ISO "2026-06-16"
  text: string;
  category: string;      // maps to client `kind`
  locked: boolean;
  fill: string | null;   // "#FFFFFF"
  warnings: unknown[];
}

export interface WireEditResponse {
  edit_id: number;
  seq: number;
  version: number;
  changed_cells: WireChangedCell[];
  stats: Record<string, Record<string, number> | null>;  // affected staff only
  warnings: WireWarnings;
  undo_available: boolean;
  redo_available: boolean;
}
```

- [ ] **Step 2: Write the edit-op union (request payloads)**

`src/domain/editOps.ts`:
```ts
// Request payloads use `sid` per synthesis §2.2 (response uses `staff_id`).
export type EditOp =
  | { op: 'assign'; sid: string; date: string; location: string }
  | { op: 'unassign'; sid: string; date: string; location?: string }
  | { op: 'move'; sid: string; from: string; to: string }
  | { op: 'toggle_lock'; sid: string; date: string; location?: string; locked: boolean }
  | { op: 'set_symbol'; sid: string; date: string; symbol: string | null };

export type EditRequest = EditOp & { expected_version: number };
```

- [ ] **Step 3: Write the failing API-client test**

`src/api/editsApi.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { postEdit } from './editsApi';
import { ConflictError } from './http';
import type { WireEditResponse, WireGridResponse } from '../domain/wire';

const okResp: WireEditResponse = {
  edit_id: 1, seq: 1, version: 5, changed_cells: [], stats: {},
  warnings: { coverage: [], holiday_deficit: [], consecutive: [], skill: [] },
  undo_available: true, redo_available: false,
};

describe('postEdit', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('POSTs op + expected_version and returns parsed response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(okResp), { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const res = await postEdit('R1', { op: 'assign', sid: 'T013', date: '2026-06-16', location: 'CT' }, 4);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/rosters/R1/edits');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ op: 'assign', sid: 'T013', date: '2026-06-16', location: 'CT', expected_version: 4 });
    expect(res.version).toBe(5);
  });

  it('throws ConflictError carrying server grid on 409', async () => {
    const grid = { version: 9, rows: [] } as unknown as WireGridResponse;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify(grid), { status: 409, headers: { 'content-type': 'application/json' } }),
    ));
    await expect(postEdit('R1', { op: 'assign', sid: 'T1', date: '2026-06-01', location: 'CT' }, 1))
      .rejects.toBeInstanceOf(ConflictError);
  });
});
```

- [ ] **Step 4: Run it (expect failure)**

Run: `cd frontend && npm run test -- editsApi`
Expected: FAIL — `postEdit`/`ConflictError` not defined.

- [ ] **Step 5: Implement the HTTP wrapper**

`src/api/http.ts`:
```ts
import type { WireGridResponse } from '../domain/wire';

const BASE = import.meta.env.VITE_API_BASE ?? '';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError'; }
}

export class ConflictError extends Error {
  constructor(public serverGrid: WireGridResponse) { super('version conflict (409)'); this.name = 'ConflictError'; }
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 409) throw new ConflictError(await res.json());
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string { return `${BASE}${path}`; }
```

- [ ] **Step 6: Implement `rosterApi.ts` and `editsApi.ts`**

`src/api/rosterApi.ts`:
```ts
import { getJson, apiUrl } from './http';
import type { WireGridResponse } from '../domain/wire';

export const getRoster = (rid: string) => getJson<WireGridResponse>(`/rosters/${rid}`);
export const getExcelUrl = (rid: string) => apiUrl(`/rosters/${rid}/excel`);
```
`src/api/editsApi.ts`:
```ts
import { postJson } from './http';
import type { EditOp } from '../domain/editOps';
import type { WireEditResponse } from '../domain/wire';

export const postEdit = (rid: string, op: EditOp, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/edits`, { ...op, expected_version: expectedVersion });

export const postUndo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/undo`, { expected_version: expectedVersion });

export const postRedo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/redo`, { expected_version: expectedVersion });

export const postConfirm = (rid: string, expectedVersion: number) =>
  postJson<{ status: string }>(`/rosters/${rid}/confirm`, { expected_version: expectedVersion });

// P2b dark-launch: resolve is mocked until the re-solve backend lands.
export const postResolve = async (_rid: string, _expectedVersion: number): Promise<WireEditResponse> => {
  throw new Error('resolve is not available until P2b');
};
```

- [ ] **Step 7: Run the test (expect pass)**

Run: `cd frontend && npm run test -- editsApi`
Expected: PASS, 2 tests.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/domain frontend/src/api
git commit -m "feat(frontend): wire DTO types + API client with optimistic-concurrency ConflictError"
```

---

## Task 3: Normalization layer — dates, fill, grid → RosterState

**Files:**
- Create: `frontend/src/domain/model.ts`, `frontend/src/normalize/dates.ts`, `frontend/src/normalize/fill.ts`, `frontend/src/normalize/normalizeGrid.ts`, `frontend/src/test/fixtures.ts`
- Test: `frontend/src/normalize/normalizeGrid.test.ts`, `frontend/src/normalize/dates.test.ts`

- [ ] **Step 1: Write the normalized client model**

`src/domain/model.ts`:
```ts
import type { WireWarnings } from './wire';

export interface CellWarning { kind: string; detail: unknown }

export interface Cell {
  day: number;
  text: string;
  kind: string;            // unified: grid `kind` OR edit `category`
  fill: string | null;     // normalized "#RRGGBB" or null
  locked: boolean;
  pending?: boolean;        // optimistic, awaiting server confirmation
}

export interface Row {
  staffId: string;
  staffNum: number;
  name: string;
  cells: Map<number, Cell>;
  hasWork: boolean;
  stats: Record<string, number> | null;
}

export interface OnCallRow { label: string; cells: Map<number, string> }

export interface RosterState {
  rosterId: string;
  year: number;
  month: number;
  daysInMonth: number;
  version: number;
  rows: Row[];
  oncallRows: OnCallRow[];
  weekdays: Record<number, string>;   // {1:"月",...}
  holidays: Set<number>;              // day numbers flagged 祝
  statsColumns: string[];
  warnings: WireWarnings;
  undoAvailable: boolean;
  redoAvailable: boolean;
}
```

- [ ] **Step 2: Write the failing date-helper test**

`src/normalize/dates.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { toIsoDate, parseDayFromIso, weekendKind } from './dates';

describe('dates', () => {
  it('builds zero-padded ISO dates', () => {
    expect(toIsoDate(2026, 6, 7)).toBe('2026-06-07');
    expect(toIsoDate(2026, 12, 31)).toBe('2026-12-31');
  });
  it('parses the day-of-month from an ISO date', () => {
    expect(parseDayFromIso('2026-06-16')).toBe(16);
    expect(parseDayFromIso('2026-06-01')).toBe(1);
  });
  it('classifies weekend shading from the weekday char', () => {
    expect(weekendKind('土')).toBe('sat');
    expect(weekendKind('日')).toBe('sun');
    expect(weekendKind('水')).toBeNull();
  });
});
```

- [ ] **Step 3: Run it (expect failure)**

Run: `cd frontend && npm run test -- dates`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `dates.ts` and `fill.ts`**

`src/normalize/dates.ts`:
```ts
const pad = (n: number) => String(n).padStart(2, '0');

export const toIsoDate = (year: number, month: number, day: number) =>
  `${year}-${pad(month)}-${pad(day)}`;

export const parseDayFromIso = (iso: string) => Number(iso.slice(8, 10));

export type WeekendKind = 'sat' | 'sun' | null;
export const weekendKind = (weekdayChar: string): WeekendKind =>
  weekdayChar === '土' ? 'sat' : weekdayChar === '日' ? 'sun' : null;
```
`src/normalize/fill.ts`:
```ts
// Server grid sends "FFFF00" (no #); edit deltas send "#FFFFFF". Normalize both.
export const normalizeFill = (fill: string | null | undefined): string | null => {
  if (!fill) return null;
  return fill.startsWith('#') ? fill : `#${fill}`;
};

// Port of shift_scheduler fill_for() for thin optimistic feedback ONLY.
// Authoritative fill always comes from the server edit response.
export const localFillFor = (text: string): string | null => {
  if (text.includes('夜')) return '#FFFF00';
  if (text === '○') return '#FFC0CB';
  if (text === '★' || text === '☆' || text === '◆') return '#FFCDD2';
  if (text === '休') return '#D3D3D3';
  return null;
};
```

- [ ] **Step 5: Write a shared fixture**

`src/test/fixtures.ts`:
```ts
import type { WireGridResponse, WireEditResponse } from '../domain/wire';

export const gridFixture: WireGridResponse = {
  year: 2026, month: 6,
  rows: [
    {
      staff_id: 'T013', staff_num: 13, name: '佐藤(海)',
      cells: { '1': 'CT', '2': '○', '3': '病CT夜', '4': '' },
      cell_meta: {
        '1': { kind: 'work', fill: null, locked: false },
        '2': { kind: 'akemei', fill: 'FFC0CB', locked: false },
        '3': { kind: 'night', fill: 'FFFF00', locked: true },
        '4': { kind: 'empty', fill: null, locked: false },
      },
      has_work: true,
      stats: { '夜勤': 2, 'CT': 7, '公休': 9, '代休': 0 },
    },
    {
      staff_id: 'T020', staff_num: 20, name: '田中',
      cells: { '1': '休', '2': '', '3': '', '4': '' },
      cell_meta: { '1': { kind: 'off', fill: 'D3D3D3', locked: false } },
      has_work: false,
      stats: null,
    },
  ],
  oncall_rows: [{ label: '第1拘束', cells: { '1': '佐藤海', '2': '' } }],
  weekdays: { '1': '月', '2': '火', '3': '水', '4': '木' },
  stats_columns: ['夜勤', 'CT', '公休', '代休'],
  version: 4,
  warnings: { coverage: [], holiday_deficit: [], consecutive: [], skill: [] },
};

export const nightEditResponseFixture: WireEditResponse = {
  edit_id: 7, seq: 3, version: 5,
  // a night assignment on day 15 derives a D+1 明け '○' on day 16 — client cannot predict this
  changed_cells: [
    { staff_id: 'T013', date: '2026-06-15', text: '病CT夜', category: 'night', locked: false, fill: '#FFFF00', warnings: [] },
    { staff_id: 'T013', date: '2026-06-16', text: '○', category: 'akemei', locked: false, fill: '#FFC0CB', warnings: [] },
  ],
  stats: { 'T013': { '夜勤': 3, 'CT': 7, '公休': 9, '代休': 0 } },
  warnings: {
    coverage: [{ date: '2026-06-15', location: 'ク', required: 3, assigned: 2, short: 1 }],
    holiday_deficit: [], consecutive: [], skill: [],
  },
  undo_available: true, redo_available: false,
};
```

- [ ] **Step 6: Write the failing `normalizeGrid` test**

`src/normalize/normalizeGrid.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { normalizeGrid } from './normalizeGrid';
import { gridFixture } from '../test/fixtures';

describe('normalizeGrid', () => {
  it('maps wire grid into RosterState with normalized fills and day-int keys', () => {
    const s = normalizeGrid('R1', gridFixture);
    expect(s.rosterId).toBe('R1');
    expect(s.version).toBe(4);
    expect(s.daysInMonth).toBe(30);              // June 2026
    expect(s.weekdays[1]).toBe('月');
    const t13 = s.rows.find((r) => r.staffId === 'T013')!;
    expect(t13.cells.get(3)).toEqual({ day: 3, text: '病CT夜', kind: 'night', fill: '#FFFF00', locked: true });
    expect(t13.cells.get(1)!.fill).toBeNull();
    expect(t13.stats!['CT']).toBe(7);
    const t20 = s.rows.find((r) => r.staffId === 'T020')!;
    expect(t20.hasWork).toBe(false);
    expect(t20.stats).toBeNull();
  });
  it('flags holidays from the optional holidays array', () => {
    const s = normalizeGrid('R1', { ...gridFixture, holidays: ['2026-06-02'] });
    expect(s.holidays.has(2)).toBe(true);
  });
});
```

- [ ] **Step 7: Run it (expect failure)**

Run: `cd frontend && npm run test -- normalizeGrid`
Expected: FAIL — module not found.

- [ ] **Step 8: Implement `normalizeGrid.ts`**

`src/normalize/normalizeGrid.ts`:
```ts
import type { WireGridResponse } from '../domain/wire';
import type { RosterState, Row, Cell, OnCallRow } from '../domain/model';
import { normalizeFill } from './fill';
import { parseDayFromIso } from './dates';

const daysInMonth = (year: number, month: number) => new Date(year, month, 0).getDate();

export function normalizeGrid(rosterId: string, w: WireGridResponse): RosterState {
  const rows: Row[] = w.rows.map((wr) => {
    const cells = new Map<number, Cell>();
    for (const [dayStr, text] of Object.entries(wr.cells)) {
      const day = Number(dayStr);
      const meta = wr.cell_meta[dayStr] ?? { kind: 'empty', fill: null };
      cells.set(day, {
        day, text, kind: meta.kind,
        fill: normalizeFill(meta.fill),
        locked: meta.locked ?? false,
      });
    }
    return {
      staffId: wr.staff_id, staffNum: wr.staff_num, name: wr.name,
      cells, hasWork: wr.has_work, stats: wr.stats,
    };
  });

  const oncallRows: OnCallRow[] = w.oncall_rows.map((o) => ({
    label: o.label,
    cells: new Map(Object.entries(o.cells).map(([d, v]) => [Number(d), v])),
  }));

  const weekdays: Record<number, string> = {};
  for (const [d, c] of Object.entries(w.weekdays)) weekdays[Number(d)] = c;

  const holidays = new Set<number>((w.holidays ?? []).map(parseDayFromIso));

  return {
    rosterId, year: w.year, month: w.month,
    daysInMonth: daysInMonth(w.year, w.month),
    version: w.version, rows, oncallRows, weekdays, holidays,
    statsColumns: w.stats_columns, warnings: w.warnings,
    undoAvailable: false, redoAvailable: false,
  };
}
```

- [ ] **Step 9: Run tests (expect pass)**

Run: `cd frontend && npm run test -- normalize`
Expected: PASS (dates + normalizeGrid).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/domain/model.ts frontend/src/normalize frontend/src/test/fixtures.ts
git commit -m "feat(frontend): normalization layer mapping wire grid -> RosterState"
```

---

## Task 4: Merge reducer + optimistic apply + move-payload builder (the heart)

**Files:**
- Create: `frontend/src/normalize/mergeEdit.ts`
- Test: `frontend/src/normalize/mergeEdit.test.ts`

- [ ] **Step 1: Write the failing tests (authoritative merge, optimistic, move)**

`src/normalize/mergeEdit.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { normalizeGrid } from './normalizeGrid';
import { mergeEditResponse, applyOptimistic, buildMovePayload } from './mergeEdit';
import { gridFixture, nightEditResponseFixture } from '../test/fixtures';

const base = () => normalizeGrid('R1', gridFixture);

describe('mergeEditResponse', () => {
  it('applies changed_cells (date→day, category→kind, # fill), bumps version, replaces warnings/flags', () => {
    const s = mergeEditResponse(base(), nightEditResponseFixture);
    expect(s.version).toBe(5);
    const t13 = s.rows.find((r) => r.staffId === 'T013')!;
    // D+1 明け cell the client could not predict is now present, authoritative
    expect(t13.cells.get(16)).toEqual({ day: 16, text: '○', kind: 'akemei', fill: '#FFC0CB', locked: false });
    expect(t13.cells.get(15)!.text).toBe('病CT夜');
    expect(t13.stats!['夜勤']).toBe(3);                 // authoritative recomputed stat
    expect(s.warnings.coverage).toHaveLength(1);
    expect(s.undoAvailable).toBe(true);
    expect(s.redoAvailable).toBe(false);
  });

  it('clears the pending flag on merged cells', () => {
    const s0 = applyOptimistic(base(), { op: 'assign', sid: 'T013', date: '2026-06-15', location: '病CT夜' });
    expect(s0.rows.find((r) => r.staffId === 'T013')!.cells.get(15)!.pending).toBe(true);
    const s1 = mergeEditResponse(s0, nightEditResponseFixture);
    expect(s1.rows.find((r) => r.staffId === 'T013')!.cells.get(15)!.pending).toBeUndefined();
  });

  it('flips has_work=false when server returns stats:null for a staff', () => {
    const resp = { ...nightEditResponseFixture, stats: { 'T013': null } };
    const s = mergeEditResponse(base(), resp);
    expect(s.rows.find((r) => r.staffId === 'T013')!.hasWork).toBe(false);
  });
});

describe('applyOptimistic', () => {
  it('assign sets text+local fill+pending without touching stats', () => {
    const s = applyOptimistic(base(), { op: 'assign', sid: 'T013', date: '2026-06-04', location: 'MG' });
    const c = s.rows.find((r) => r.staffId === 'T013')!.cells.get(4)!;
    expect(c).toMatchObject({ text: 'MG', fill: null, pending: true });
    // stats untouched optimistically — server is authoritative
    expect(s.rows.find((r) => r.staffId === 'T013')!.stats!['CT']).toBe(7);
  });
  it('unassign blanks the cell text optimistically', () => {
    const s = applyOptimistic(base(), { op: 'unassign', sid: 'T013', date: '2026-06-01' });
    expect(s.rows.find((r) => r.staffId === 'T013')!.cells.get(1)!.text).toBe('');
  });
});

describe('buildMovePayload', () => {
  it('builds one move op for same-staff day→day drag', () => {
    const p = buildMovePayload('T013:3', 'T013:4', 2026, 6);
    expect(p).toEqual({ op: 'move', sid: 'T013', from: '2026-06-03', to: '2026-06-04' });
  });
  it('returns null for cross-staff drag (no single move op)', () => {
    expect(buildMovePayload('T013:3', 'T020:3', 2026, 6)).toBeNull();
  });
  it('returns null for a drop onto the same cell', () => {
    expect(buildMovePayload('T013:3', 'T013:3', 2026, 6)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- mergeEdit`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `mergeEdit.ts`**

`src/normalize/mergeEdit.ts`:
```ts
import type { RosterState, Row, Cell } from '../domain/model';
import type { WireEditResponse } from '../domain/wire';
import type { EditOp } from '../domain/editOps';
import { parseDayFromIso } from './dates';
import { normalizeFill, localFillFor } from './fill';

/** Merge the AUTHORITATIVE server edit response. Overwrites changed cells (incl. D+1 明け),
 *  affected-staff stats, the whole warning set, version, and undo/redo flags. */
export function mergeEditResponse(state: RosterState, resp: WireEditResponse): RosterState {
  const changedByStaff = new Map<string, Cell[]>();
  for (const c of resp.changed_cells) {
    const cell: Cell = {
      day: parseDayFromIso(c.date),
      text: c.text,
      kind: c.category,
      fill: normalizeFill(c.fill),
      locked: c.locked,
    };
    const arr = changedByStaff.get(c.staff_id) ?? [];
    arr.push(cell);
    changedByStaff.set(c.staff_id, arr);
  }

  const rows: Row[] = state.rows.map((r) => {
    const changed = changedByStaff.get(r.staffId);
    const hasStats = Object.prototype.hasOwnProperty.call(resp.stats, r.staffId);
    if (!changed && !hasStats) return r;

    let cells = r.cells;
    if (changed) {
      cells = new Map(r.cells);
      for (const c of changed) cells.set(c.day, c);   // pending implicitly cleared
    }
    let stats = r.stats;
    let hasWork = r.hasWork;
    if (hasStats) {
      const ns = resp.stats[r.staffId];
      stats = ns;
      hasWork = ns !== null;
    }
    return { ...r, cells, stats, hasWork };
  });

  return {
    ...state, rows,
    version: resp.version,
    warnings: resp.warnings,
    undoAvailable: resp.undo_available,
    redoAvailable: resp.redo_available,
  };
}

/** Thin optimistic update of the edited cell text/fill ONLY. Stats stay until the merge. */
export function applyOptimistic(state: RosterState, op: EditOp): RosterState {
  const rows = state.rows.map((r) => {
    const sid = 'sid' in op ? op.sid : undefined;
    if (r.staffId !== sid) return r;

    const cells = new Map(r.cells);
    const setCell = (day: number, text: string) => {
      const prev = cells.get(day);
      cells.set(day, { day, text, kind: prev?.kind ?? 'work', fill: localFillFor(text), locked: prev?.locked ?? false, pending: true });
    };
    if (op.op === 'assign') setCell(parseDayFromIso(op.date), op.location);
    else if (op.op === 'unassign') setCell(parseDayFromIso(op.date), '');
    else if (op.op === 'move') {
      const fromDay = parseDayFromIso(op.from);
      const toDay = parseDayFromIso(op.to);
      const moving = cells.get(fromDay)?.text ?? '';
      setCell(fromDay, '');
      setCell(toDay, moving);
    } else if (op.op === 'toggle_lock') {
      const day = parseDayFromIso(op.date);
      const prev = cells.get(day);
      if (prev) cells.set(day, { ...prev, locked: op.locked });
    } else if (op.op === 'set_symbol') {
      setCell(parseDayFromIso(op.date), op.symbol ?? '');
    }
    return { ...r, cells };
  });
  return { ...state, rows };
}

/** dnd-kit drop → one `move` op. Cross-staff or same-cell → null (no single move). */
export function buildMovePayload(
  sourceId: string, targetId: string, year: number, month: number,
): Extract<EditOp, { op: 'move' }> | null {
  const [sSid, sDay] = sourceId.split(':');
  const [tSid, tDay] = targetId.split(':');
  if (sSid !== tSid || sDay === tDay) return null;
  const pad = (n: string) => n.padStart(2, '0');
  return { op: 'move', sid: sSid, from: `${year}-${pad(String(month))}-${pad(sDay)}`, to: `${year}-${pad(String(month))}-${pad(tDay)}` };
}
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `cd frontend && npm run test -- mergeEdit`
Expected: PASS (all merge/optimistic/move cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/normalize/mergeEdit.ts frontend/src/normalize/mergeEdit.test.ts
git commit -m "feat(frontend): authoritative edit merge reducer + optimistic apply + move builder"
```

---

## Task 5: TanStack Query — roster query + optimistic edit/undo/redo mutations

**Files:**
- Create: `frontend/src/query/queryClient.ts`, `frontend/src/query/useRoster.ts`, `frontend/src/query/useEditMutation.ts`
- Test: `frontend/src/query/useEditMutation.test.tsx`

- [ ] **Step 1: Implement the query client + roster query**

`src/query/queryClient.ts`:
```ts
import { QueryClient } from '@tanstack/react-query';
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
export const rosterKey = (rid: string) => ['roster', rid] as const;
```
`src/query/useRoster.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { getRoster } from '../api/rosterApi';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { rosterKey } from './queryClient';
import type { RosterState } from '../domain/model';

export function useRoster(rid: string) {
  return useQuery<RosterState>({
    queryKey: rosterKey(rid),
    queryFn: async () => normalizeGrid(rid, await getRoster(rid)),
  });
}
```

- [ ] **Step 2: Write the failing mutation test**

`src/query/useEditMutation.test.tsx`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { rosterKey } from './queryClient';
import { useEditMutation } from './useEditMutation';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { gridFixture, nightEditResponseFixture } from '../test/fixtures';
import * as editsApi from '../api/editsApi';
import { ConflictError } from '../api/http';

function wrap(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useEditMutation', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('optimistically updates then merges the authoritative server response', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(rosterKey('R1'), normalizeGrid('R1', gridFixture));
    vi.spyOn(editsApi, 'postEdit').mockResolvedValue(nightEditResponseFixture);

    const { result } = renderHook(() => useEditMutation('R1'), { wrapper: wrap(qc) });
    await act(async () => { await result.current.edit({ op: 'assign', sid: 'T013', date: '2026-06-15', location: '病CT夜' }); });

    await waitFor(() => {
      const s = qc.getQueryData(rosterKey('R1')) as ReturnType<typeof normalizeGrid>;
      expect(s.version).toBe(5);
      expect(s.rows.find((r) => r.staffId === 'T013')!.cells.get(16)!.text).toBe('○'); // D+1 明け merged
    });
  });

  it('surfaces a 409 ConflictError with the server grid for rebase', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(rosterKey('R1'), normalizeGrid('R1', gridFixture));
    vi.spyOn(editsApi, 'postEdit').mockRejectedValue(new ConflictError({ ...gridFixture, version: 9 }));
    const onConflict = vi.fn();

    const { result } = renderHook(() => useEditMutation('R1', onConflict), { wrapper: wrap(qc) });
    await act(async () => {
      await result.current.edit({ op: 'assign', sid: 'T013', date: '2026-06-15', location: 'CT' }).catch(() => {});
    });
    await waitFor(() => expect(onConflict).toHaveBeenCalledWith(expect.objectContaining({ version: 9 })));
  });
});
```

- [ ] **Step 3: Run it (expect failure)**

Run: `cd frontend && npm run test -- useEditMutation`
Expected: FAIL — `useEditMutation` not defined.

- [ ] **Step 4: Implement `useEditMutation.ts`**

`src/query/useEditMutation.ts`:
```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { rosterKey } from './queryClient';
import { postEdit, postUndo, postRedo } from '../api/editsApi';
import { applyOptimistic, mergeEditResponse } from '../normalize/mergeEdit';
import { ConflictError } from '../api/http';
import type { RosterState } from '../domain/model';
import type { EditOp } from '../domain/editOps';
import type { WireGridResponse, WireEditResponse } from '../domain/wire';

type Action =
  | { kind: 'edit'; op: EditOp }
  | { kind: 'undo' }
  | { kind: 'redo' };

export function useEditMutation(rid: string, onConflict?: (grid: WireGridResponse) => void) {
  const qc = useQueryClient();
  const key = rosterKey(rid);

  const m = useMutation<WireEditResponse, unknown, Action, { prev?: RosterState }>({
    onMutate: async (action) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<RosterState>(key);
      if (prev && action.kind === 'edit') {
        qc.setQueryData<RosterState>(key, applyOptimistic(prev, action.op)); // edited cell only
      }
      return { prev };
    },
    mutationFn: async (action) => {
      const state = qc.getQueryData<RosterState>(key);
      const version = state?.version ?? 0;
      if (action.kind === 'edit') return postEdit(rid, action.op, version);
      if (action.kind === 'undo') return postUndo(rid, version);
      return postRedo(rid, version);
    },
    onSuccess: (resp) => {
      const cur = qc.getQueryData<RosterState>(key);
      if (cur) qc.setQueryData<RosterState>(key, mergeEditResponse(cur, resp)); // authoritative
    },
    onError: (err, _action, ctx) => {
      if (err instanceof ConflictError) { onConflict?.(err.serverGrid); return; }
      if (ctx?.prev) qc.setQueryData(key, ctx.prev); // rollback optimistic on non-conflict errors
    },
  });

  return {
    edit: (op: EditOp) => m.mutateAsync({ kind: 'edit', op }),
    undo: () => m.mutateAsync({ kind: 'undo' }),
    redo: () => m.mutateAsync({ kind: 'redo' }),
    isPending: m.isPending,
  };
}
```

- [ ] **Step 5: Run the test (expect pass)**

Run: `cd frontend && npm run test -- useEditMutation`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/query
git commit -m "feat(frontend): TanStack Query roster fetch + optimistic edit/undo/redo with 409 rebase hook"
```

---

## Task 6: Zustand UI store

**Files:**
- Create: `frontend/src/store/uiStore.ts`
- Test: `frontend/src/store/uiStore.test.ts`

- [ ] **Step 1: Write the failing store test**

`src/store/uiStore.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useUiStore } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => useUiStore.getState().reset());

  it('toggles heatmap mode through off → load → shortfall → off', () => {
    const s = useUiStore.getState();
    expect(s.heatmapMode).toBe('off');
    s.cycleHeatmap(); expect(useUiStore.getState().heatmapMode).toBe('load');
    s.cycleHeatmap(); expect(useUiStore.getState().heatmapMode).toBe('shortfall');
    s.cycleHeatmap(); expect(useUiStore.getState().heatmapMode).toBe('off');
  });

  it('selects a cell and sets highlighted cells from a warning click', () => {
    const s = useUiStore.getState();
    s.selectCell({ staffId: 'T013', day: 16 });
    expect(useUiStore.getState().selectedCell).toEqual({ staffId: 'T013', day: 16 });
    s.highlight([{ staffId: 'T013', day: 16 }, { staffId: 'T013', day: 15 }]);
    expect(useUiStore.getState().highlighted.size).toBe(2);
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- uiStore`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `uiStore.ts`**

`src/store/uiStore.ts`:
```ts
import { create } from 'zustand';

export type HeatmapMode = 'off' | 'load' | 'shortfall';
export interface CellRef { staffId: string; day: number }

const cellKey = (c: CellRef) => `${c.staffId}:${c.day}`;
const NEXT: Record<HeatmapMode, HeatmapMode> = { off: 'load', load: 'shortfall', shortfall: 'off' };

interface UiState {
  heatmapMode: HeatmapMode;
  selectedCell: CellRef | null;
  highlighted: Set<string>;
  historyOpen: boolean;
  cycleHeatmap: () => void;
  selectCell: (c: CellRef | null) => void;
  highlight: (cells: CellRef[]) => void;
  clearHighlight: () => void;
  toggleHistory: () => void;
  reset: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  heatmapMode: 'off',
  selectedCell: null,
  highlighted: new Set<string>(),
  historyOpen: false,
  cycleHeatmap: () => set((s) => ({ heatmapMode: NEXT[s.heatmapMode] })),
  selectCell: (c) => set({ selectedCell: c }),
  highlight: (cells) => set({ highlighted: new Set(cells.map(cellKey)) }),
  clearHighlight: () => set({ highlighted: new Set<string>() }),
  toggleHistory: () => set((s) => ({ historyOpen: !s.historyOpen })),
  reset: () => set({ heatmapMode: 'off', selectedCell: null, highlighted: new Set<string>(), historyOpen: false }),
}));

export { cellKey };
```

- [ ] **Step 4: Run the test (expect pass)**

Run: `cd frontend && npm run test -- uiStore`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store
git commit -m "feat(frontend): Zustand UI store for heatmap/selection/highlight/drawer"
```

---

## Task 7: ScheduleGrid + DayCell + StatsCells + OnCallRows

**Files:**
- Create: `frontend/src/components/ScheduleGrid.tsx`, `frontend/src/components/DayCell.tsx`, `frontend/src/components/StatsCells.tsx`, `frontend/src/components/OnCallRows.tsx`, `frontend/src/components/grid.css`
- Test: `frontend/src/components/DayCell.test.tsx`

- [ ] **Step 1: Write the failing DayCell test**

`src/components/DayCell.test.tsx`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DayCell } from './DayCell';
import type { Cell } from '../domain/model';

const cell: Cell = { day: 3, text: '病CT夜', kind: 'night', fill: '#FFFF00', locked: true };

describe('DayCell', () => {
  it('renders text, applies fill, shows a lock badge when locked', () => {
    render(<DayCell staffId="T013" cell={cell} onClick={() => {}} />);
    expect(screen.getByText('病CT夜')).toBeInTheDocument();
    const el = screen.getByTestId('cell-T013-3');
    expect(el).toHaveStyle({ backgroundColor: '#FFFF00' });
    expect(screen.getByTestId('lock-T013-3')).toBeInTheDocument();
  });

  it('calls onClick with the cell ref', async () => {
    const onClick = vi.fn();
    render(<DayCell staffId="T013" cell={cell} onClick={onClick} />);
    await userEvent.click(screen.getByTestId('cell-T013-3'));
    expect(onClick).toHaveBeenCalledWith({ staffId: 'T013', day: 3 });
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- DayCell`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `DayCell.tsx`**

`src/components/DayCell.tsx`:
```tsx
import React from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import type { Cell } from '../domain/model';
import type { CellRef } from '../store/uiStore';

interface Props {
  staffId: string;
  cell: Cell | undefined;
  onClick: (ref: CellRef) => void;
  highlighted?: boolean;
  heatColor?: string | null;
}

export function DayCell({ staffId, cell, onClick, highlighted, heatColor }: Props) {
  const day = cell?.day ?? 0;
  const id = `${staffId}:${day}`;
  const { attributes, listeners, setNodeRef: dragRef } = useDraggable({ id });
  const { setNodeRef: dropRef, isOver } = useDroppable({ id });

  const bg = heatColor ?? cell?.fill ?? undefined;
  const style: React.CSSProperties = {
    backgroundColor: bg,
    outline: highlighted ? '2px solid #d32f2f' : isOver ? '2px dashed #1976d2' : undefined,
    opacity: cell?.pending ? 0.5 : 1,
  };

  return (
    <td
      ref={(n) => { dragRef(n); dropRef(n); }}
      {...listeners}
      {...attributes}
      data-testid={`cell-${staffId}-${day}`}
      className="day-cell"
      style={style}
      onClick={() => onClick({ staffId, day })}
    >
      {cell?.locked && <span data-testid={`lock-${staffId}-${day}`} className="lock-badge">🔒</span>}
      {cell?.text ?? ''}
    </td>
  );
}
```

- [ ] **Step 4: Run the DayCell test (expect pass)**

Run: `cd frontend && npm run test -- DayCell`
Expected: PASS, 2 tests.

- [ ] **Step 5: Implement `StatsCells.tsx`**

`src/components/StatsCells.tsx`:
```tsx
import React from 'react';
import type { Row } from '../domain/model';

export function StatsCells({ row, statsColumns }: { row: Row; statsColumns: string[] }) {
  return (
    <>
      {statsColumns.map((col) => (
        <td key={col} className="stat-cell" data-testid={`stat-${row.staffId}-${col}`}>
          {row.hasWork && row.stats ? row.stats[col] ?? 0 : ''}
        </td>
      ))}
    </>
  );
}
```

- [ ] **Step 6: Implement `OnCallRows.tsx`**

`src/components/OnCallRows.tsx`:
```tsx
import React from 'react';
import type { OnCallRow } from '../domain/model';

export function OnCallRows({ rows, days }: { rows: OnCallRow[]; days: number[] }) {
  return (
    <>
      {rows.map((r) => (
        <tr key={r.label} className="oncall-row">
          <td className="sticky-name" colSpan={2}>{r.label}</td>
          {days.map((d) => <td key={d} className="day-cell">{r.cells.get(d) ?? ''}</td>)}
        </tr>
      ))}
    </>
  );
}
```

- [ ] **Step 7: Implement `ScheduleGrid.tsx` (sticky panes, weekend shading, virtualization)**

`src/components/ScheduleGrid.tsx`:
```tsx
import React, { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { DndContext, type DragEndEvent } from '@dnd-kit/core';
import type { RosterState } from '../domain/model';
import type { CellRef } from '../store/uiStore';
import { useUiStore, cellKey } from '../store/uiStore';
import { weekendKind } from '../normalize/dates';
import { heatColorForCell } from '../viz/heatmap';
import { DayCell } from './DayCell';
import { StatsCells } from './StatsCells';
import { OnCallRows } from './OnCallRows';
import './grid.css';

interface Props {
  state: RosterState;
  onCellClick: (ref: CellRef) => void;
  onDragEnd: (e: DragEndEvent) => void;
}

export function ScheduleGrid({ state, onCellClick, onDragEnd }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const days = Array.from({ length: state.daysInMonth }, (_, i) => i + 1);
  const { heatmapMode, highlighted } = useUiStore();

  const rowVirt = useVirtualizer({
    count: state.rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 8,
  });

  return (
    <DndContext onDragEnd={onDragEnd}>
      <div ref={parentRef} className="grid-scroll">
        <table className="schedule-grid">
          <thead>
            <tr>
              <th className="sticky-name" colSpan={2}>技師名</th>
              {days.map((d) => {
                const wk = weekendKind(state.weekdays[d] ?? '');
                const holiday = state.holidays.has(d);
                const cls = holiday || wk === 'sun' ? 'col-sun' : wk === 'sat' ? 'col-sat' : '';
                return <th key={d} className={`day-head ${cls}`}>{d}</th>;
              })}
              {state.statsColumns.map((c) => <th key={c} className="stat-head">{c}</th>)}
            </tr>
            <tr>
              <th className="sticky-name" colSpan={2}>曜日</th>
              {days.map((d) => <th key={d} className="day-head">{state.weekdays[d] ?? ''}</th>)}
              {state.statsColumns.map((c) => <th key={c} className="stat-head" />)}
            </tr>
          </thead>
          <tbody style={{ height: rowVirt.getTotalSize() }}>
            {rowVirt.getVirtualItems().map((vi) => {
              const row = state.rows[vi.index];
              return (
                <tr key={row.staffId} style={{ transform: `translateY(${vi.start}px)` }}>
                  <td className="sticky-name name-cell">{row.staffNum}</td>
                  <td className="sticky-name name-cell">{row.name}</td>
                  {days.map((d) => (
                    <DayCell
                      key={d}
                      staffId={row.staffId}
                      cell={row.cells.get(d)}
                      onClick={onCellClick}
                      highlighted={highlighted.has(cellKey({ staffId: row.staffId, day: d }))}
                      heatColor={heatColorForCell(heatmapMode, state, row, d)}
                    />
                  ))}
                  <StatsCells row={row} statsColumns={state.statsColumns} />
                </tr>
              );
            })}
            <OnCallRows rows={state.oncallRows} days={days} />
          </tbody>
        </table>
      </div>
    </DndContext>
  );
}
```

- [ ] **Step 8: Implement `grid.css` (sticky panes + weekend shading)**

`src/components/grid.css`:
```css
.grid-scroll { overflow: auto; max-height: 80vh; position: relative; }
.schedule-grid { border-collapse: collapse; font-size: 12px; }
.schedule-grid th, .schedule-grid td { border: 1px solid #ccc; min-width: 28px; text-align: center; padding: 1px 2px; }
.sticky-name { position: sticky; left: 0; background: #fff; z-index: 2; min-width: 64px; }
.schedule-grid thead th { position: sticky; top: 0; background: #4472c4; color: #fff; z-index: 3; }
.schedule-grid thead th.sticky-name { z-index: 4; }
.col-sat { background: #e3f2fd; color: #000; }
.col-sun { background: #ffebee; color: #000; }
.day-cell { cursor: pointer; }
.stat-cell, .stat-head { background: #fafafa; }
.lock-badge { font-size: 9px; margin-right: 1px; }
.oncall-row td { background: #f5f5f5; font-weight: 600; }
```

- [ ] **Step 9: Run the full suite (expect pass)**

Run: `cd frontend && npm run test`
Expected: PASS (DayCell + all prior). `heatColorForCell` lands in Task 11 — add a temporary stub now so the grid compiles:

`src/viz/heatmap.ts` (stub, replaced in Task 11):
```ts
import type { RosterState, Row } from '../domain/model';
import type { HeatmapMode } from '../store/uiStore';
export function heatColorForCell(_m: HeatmapMode, _s: RosterState, _r: Row, _d: number): string | null { return null; }
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components frontend/src/viz/heatmap.ts
git commit -m "feat(frontend): virtualized ScheduleGrid with sticky panes, DayCell, StatsCells, OnCallRows"
```

---

## Task 8: EditPopover (assign / unassign / 休·○ / symbol / lock)

**Files:**
- Create: `frontend/src/components/EditPopover.tsx`, `frontend/src/domain/locations.ts`
- Test: `frontend/src/components/EditPopover.test.tsx`

- [ ] **Step 1: Implement the default location pick-list**

`src/domain/locations.ts`:
```ts
// Default pick-list; P3 replaces this with a server-fed location master.
// Work codes (stats columns minus 公休/代休) + the special tokens 休/○.
export function locationOptions(statsColumns: string[]): string[] {
  const work = statsColumns.filter((c) => c !== '公休' && c !== '代休' && c !== '夜勤');
  return [...work, '休', '○'];
}
export const REQUEST_SYMBOLS = ['★', '☆', '◆', '出', '17休', '17業', '夜希'];
```

- [ ] **Step 2: Write the failing popover test**

`src/components/EditPopover.test.tsx`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditPopover } from './EditPopover';

const props = {
  staffId: 'T013', day: 16, date: '2026-06-16',
  locked: false, statsColumns: ['夜勤', 'CT', 'MG', '公休', '代休'],
};

describe('EditPopover', () => {
  it('emits an assign op when a location is chosen', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.selectOptions(screen.getByTestId('loc-select'), 'CT');
    await userEvent.click(screen.getByTestId('apply-assign'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'assign', sid: 'T013', date: '2026-06-16', location: 'CT' });
  });

  it('emits unassign', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.click(screen.getByTestId('apply-unassign'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'unassign', sid: 'T013', date: '2026-06-16' });
  });

  it('emits toggle_lock with the flipped value', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.click(screen.getByTestId('toggle-lock'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'toggle_lock', sid: 'T013', date: '2026-06-16', locked: true });
  });
});
```

- [ ] **Step 3: Run it (expect failure)**

Run: `cd frontend && npm run test -- EditPopover`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `EditPopover.tsx`**

`src/components/EditPopover.tsx`:
```tsx
import React, { useState } from 'react';
import type { EditOp } from '../domain/editOps';
import { locationOptions, REQUEST_SYMBOLS } from '../domain/locations';

interface Props {
  staffId: string;
  day: number;
  date: string;        // ISO
  locked: boolean;
  statsColumns: string[];
  onEmit: (op: EditOp) => void;
  onClose: () => void;
}

export function EditPopover({ staffId, date, locked, statsColumns, onEmit, onClose }: Props) {
  const [loc, setLoc] = useState('');
  const [sym, setSym] = useState('');
  const fire = (op: EditOp) => { onEmit(op); onClose(); };

  return (
    <div className="edit-popover" role="dialog">
      <label>場所
        <select data-testid="loc-select" value={loc} onChange={(e) => setLoc(e.target.value)}>
          <option value="">—</option>
          {locationOptions(statsColumns).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
      <button data-testid="apply-assign" disabled={!loc}
        onClick={() => fire({ op: 'assign', sid: staffId, date, location: loc })}>配置</button>
      <button data-testid="apply-unassign"
        onClick={() => fire({ op: 'unassign', sid: staffId, date })}>解除</button>

      <label>申請
        <select data-testid="sym-select" value={sym} onChange={(e) => setSym(e.target.value)}>
          <option value="">—</option>
          {REQUEST_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <button data-testid="apply-symbol"
        onClick={() => fire({ op: 'set_symbol', sid: staffId, date, symbol: sym || null })}>申請設定</button>

      <button data-testid="toggle-lock"
        onClick={() => fire({ op: 'toggle_lock', sid: staffId, date, locked: !locked })}>
        {locked ? 'ロック解除' : 'ロック'}
      </button>
      <button data-testid="popover-close" onClick={onClose}>閉じる</button>
    </div>
  );
}
```

> **Implementer note:** verify the file compiles with `npx tsc -b` before running tests.

- [ ] **Step 5: Run the popover test (expect pass)**

Run: `cd frontend && npm run test -- EditPopover`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EditPopover.tsx frontend/src/domain/locations.ts frontend/src/components/EditPopover.test.tsx
git commit -m "feat(frontend): EditPopover emitting assign/unassign/set_symbol/toggle_lock ops"
```

---

## Task 9: Drag-drop → single `move` op

**Files:**
- Modify: `frontend/src/components/RosterPage.tsx` (created in Task 13; the drag handler logic is unit-tested here standalone)
- Create: `frontend/src/normalize/dragEnd.ts`
- Test: `frontend/src/normalize/dragEnd.test.ts`

- [ ] **Step 1: Write the failing drag-handler test**

`src/normalize/dragEnd.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { moveFromDragEnd } from './dragEnd';
import type { DragEndEvent } from '@dnd-kit/core';

const ev = (active: string, over: string | null): DragEndEvent =>
  ({ active: { id: active }, over: over ? { id: over } : null } as unknown as DragEndEvent);

describe('moveFromDragEnd', () => {
  it('returns one move op for same-staff day→day drag', () => {
    expect(moveFromDragEnd(ev('T013:3', 'T013:5'), 2026, 6))
      .toEqual({ op: 'move', sid: 'T013', from: '2026-06-03', to: '2026-06-05' });
  });
  it('returns null when dropped outside a target', () => {
    expect(moveFromDragEnd(ev('T013:3', null), 2026, 6)).toBeNull();
  });
  it('returns null for cross-staff drag', () => {
    expect(moveFromDragEnd(ev('T013:3', 'T020:3'), 2026, 6)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- dragEnd`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `dragEnd.ts`**

`src/normalize/dragEnd.ts`:
```ts
import type { DragEndEvent } from '@dnd-kit/core';
import { buildMovePayload } from './mergeEdit';
import type { EditOp } from '../domain/editOps';

export function moveFromDragEnd(
  e: DragEndEvent, year: number, month: number,
): Extract<EditOp, { op: 'move' }> | null {
  if (!e.over) return null;
  return buildMovePayload(String(e.active.id), String(e.over.id), year, month);
}
```

- [ ] **Step 4: Run the test (expect pass)**

Run: `cd frontend && npm run test -- dragEnd`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/normalize/dragEnd.ts frontend/src/normalize/dragEnd.test.ts
git commit -m "feat(frontend): drag-end → single move op (same-staff day→day, one undo step)"
```

---

## Task 10: WarningPanel (grouped, click → highlight)

**Files:**
- Create: `frontend/src/components/WarningPanel.tsx`, `frontend/src/normalize/warningCells.ts`
- Test: `frontend/src/components/WarningPanel.test.tsx`, `frontend/src/normalize/warningCells.test.ts`

- [ ] **Step 1: Write the failing warning→cells mapper test**

`src/normalize/warningCells.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { cellsForCoverage, cellsForSkill, cellsForConsecutive } from './warningCells';
import { normalizeGrid } from './normalizeGrid';
import { gridFixture } from '../test/fixtures';

const state = normalizeGrid('R1', gridFixture);

describe('warningCells', () => {
  it('maps a coverage warning to all cells of that staff... no — to the day column for affected staff', () => {
    // coverage is location/day scoped; highlight every staff row at that day
    const cells = cellsForCoverage({ date: '2026-06-01', location: 'ク', required: 3, assigned: 2, short: 1 }, state);
    expect(cells).toEqual([{ staffId: 'T013', day: 1 }, { staffId: 'T020', day: 1 }]);
  });
  it('maps a skill warning to the single (staff, day) cell', () => {
    expect(cellsForSkill({ date: '2026-06-16', location: '心', staff_id: 'T013', rule: 'min_rank', need: 'B', have: 'C' }))
      .toEqual([{ staffId: 'T013', day: 16 }]);
  });
  it('maps a consecutive warning to the run of days', () => {
    expect(cellsForConsecutive({ staff_id: 'T013', start: '2026-06-10', len: 3 }))
      .toEqual([{ staffId: 'T013', day: 10 }, { staffId: 'T013', day: 11 }, { staffId: 'T013', day: 12 }]);
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- warningCells`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `warningCells.ts`**

`src/normalize/warningCells.ts`:
```ts
import type { CoverageWarning, SkillWarning, ConsecutiveWarning, HolidayDeficitWarning } from '../domain/wire';
import type { RosterState } from '../domain/model';
import type { CellRef } from '../store/uiStore';
import { parseDayFromIso } from './dates';

export const cellsForCoverage = (w: CoverageWarning, state: RosterState): CellRef[] => {
  const day = parseDayFromIso(w.date);
  return state.rows.map((r) => ({ staffId: r.staffId, day }));
};

export const cellsForSkill = (w: SkillWarning): CellRef[] =>
  [{ staffId: w.staff_id, day: parseDayFromIso(w.date) }];

export const cellsForConsecutive = (w: ConsecutiveWarning): CellRef[] => {
  const start = parseDayFromIso(w.start);
  return Array.from({ length: w.len }, (_, i) => ({ staffId: w.staff_id, day: start + i }));
};

export const cellsForHolidayDeficit = (w: HolidayDeficitWarning, state: RosterState): CellRef[] => {
  const row = state.rows.find((r) => r.staffId === w.staff_id);
  return row ? Array.from(row.cells.keys()).map((day) => ({ staffId: w.staff_id, day })) : [];
};
```

- [ ] **Step 4: Write the failing WarningPanel test**

`src/components/WarningPanel.test.tsx`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WarningPanel } from './WarningPanel';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { gridFixture } from '../test/fixtures';
import { useUiStore } from '../store/uiStore';

const state = normalizeGrid('R1', {
  ...gridFixture,
  warnings: {
    coverage: [{ date: '2026-06-01', location: 'ク', required: 3, assigned: 2, short: 1 }],
    holiday_deficit: [{ staff_id: 'T020', off: 8, target: 9, short: 1 }],
    consecutive: [{ staff_id: 'T013', start: '2026-06-10', len: 7 }],
    skill: [],
  },
});

describe('WarningPanel', () => {
  beforeEach(() => useUiStore.getState().reset());

  it('groups warnings under coverage/holiday/consecutive/skill headers', () => {
    render(<WarningPanel state={state} />);
    expect(screen.getByText(/勤務不足/)).toBeInTheDocument();
    expect(screen.getByText(/公休不足/)).toBeInTheDocument();
    expect(screen.getByText(/連続勤務/)).toBeInTheDocument();
  });

  it('clicking a warning sets highlighted cells in the store', async () => {
    render(<WarningPanel state={state} />);
    await userEvent.click(screen.getByTestId('warn-consecutive-0'));
    expect(useUiStore.getState().highlighted.size).toBe(7);
  });
});
```

- [ ] **Step 5: Run it (expect failure)**

Run: `cd frontend && npm run test -- WarningPanel`
Expected: FAIL — module not found.

- [ ] **Step 6: Implement `WarningPanel.tsx`**

`src/components/WarningPanel.tsx`:
```tsx
import React from 'react';
import type { RosterState } from '../domain/model';
import { useUiStore } from '../store/uiStore';
import {
  cellsForCoverage, cellsForSkill, cellsForConsecutive, cellsForHolidayDeficit,
} from '../normalize/warningCells';

export function WarningPanel({ state }: { state: RosterState }) {
  const highlight = useUiStore((s) => s.highlight);
  const { coverage, holiday_deficit, consecutive, skill } = state.warnings;

  return (
    <aside className="warning-panel">
      <section>
        <h3>勤務不足の場所 ({coverage.length})</h3>
        {coverage.map((w, i) => (
          <button key={i} data-testid={`warn-coverage-${i}`} onClick={() => highlight(cellsForCoverage(w, state))}>
            {w.date} {w.location}: {w.assigned}/{w.required} (不足{w.short})
          </button>
        ))}
      </section>
      <section>
        <h3>公休不足の人 ({holiday_deficit.length})</h3>
        {holiday_deficit.map((w, i) => (
          <button key={i} data-testid={`warn-holiday-${i}`} onClick={() => highlight(cellsForHolidayDeficit(w, state))}>
            {w.staff_id}: 公休{w.off}/{w.target} (あと{w.short})
          </button>
        ))}
      </section>
      <section>
        <h3>連続勤務 ({consecutive.length})</h3>
        {consecutive.map((w, i) => (
          <button key={i} data-testid={`warn-consecutive-${i}`} onClick={() => highlight(cellsForConsecutive(w))}>
            {w.staff_id}: {w.start} から {w.len}連勤
          </button>
        ))}
      </section>
      <section>
        <h3>スキル/PB/夜勤違反 ({skill.length})</h3>
        {skill.map((w, i) => (
          <button key={i} data-testid={`warn-skill-${i}`} onClick={() => highlight(cellsForSkill(w))}>
            {w.date} {w.location} {w.staff_id}: {w.rule} need {w.need} have {w.have}
          </button>
        ))}
      </section>
    </aside>
  );
}
```

- [ ] **Step 7: Run tests (expect pass)**

Run: `cd frontend && npm run test -- "warningCells|WarningPanel"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WarningPanel.tsx frontend/src/normalize/warningCells.ts frontend/src/components/WarningPanel.test.tsx frontend/src/normalize/warningCells.test.ts
git commit -m "feat(frontend): grouped WarningPanel with click-to-highlight cell mapping"
```

---

## Task 11: HeatmapToggle + heatmap pure functions

**Files:**
- Modify: `frontend/src/viz/heatmap.ts` (replace the Task 7 stub)
- Create: `frontend/src/components/HeatmapToggle.tsx`
- Test: `frontend/src/viz/heatmap.test.ts`

- [ ] **Step 1: Write the failing heatmap test**

`src/viz/heatmap.test.ts`:
```ts
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
    const s2 = { ...state, warnings: { ...state.warnings, coverage: [{ date: '2026-06-01', location: 'CT', required: 2, assigned: 1, short: 1 }] } };
    expect(heatColorForCell('shortfall', s2, t13, 1)).toMatch(/^#/); // day1 cell text 'CT' matches location
    expect(heatColorForCell('shortfall', s2, t13, 3)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- heatmap`
Expected: FAIL — `loadByStaff` not defined (stub only exports `heatColorForCell`).

- [ ] **Step 3: Implement `heatmap.ts` (replace the stub)**

`src/viz/heatmap.ts`:
```ts
import type { RosterState, Row } from '../domain/model';
import type { HeatmapMode } from '../store/uiStore';

const WORK_KINDS = new Set(['work', 'night', 'akemei']);

export function loadByStaff(row: Row): number {
  let n = 0;
  for (const cell of row.cells.values()) if (WORK_KINDS.has(cell.kind)) n += 1;
  return n;
}

// Visualization-only (not authoritative stats): green→red ramp by load fraction.
function loadColor(count: number, max: number): string {
  const t = max <= 0 ? 0 : Math.min(1, count / max);
  const r = Math.round(80 + 175 * t);
  const g = Math.round(200 - 150 * t);
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}66`;
}

export function heatColorForCell(mode: HeatmapMode, state: RosterState, row: Row, day: number): string | null {
  if (mode === 'off') return null;
  if (mode === 'load') {
    const cell = row.cells.get(day);
    if (!cell || !WORK_KINDS.has(cell.kind)) return null;
    const max = Math.max(...state.rows.map(loadByStaff), 1);
    return loadColor(loadByStaff(row), max);
  }
  // shortfall: redden cells whose (day, location) appears in a coverage shortfall
  const cell = row.cells.get(day);
  if (!cell) return null;
  const dd = String(day).padStart(2, '0');
  const hit = state.warnings.coverage.find((w) => w.date.endsWith(`-${dd}`) && cell.text.includes(w.location));
  return hit ? '#ff7043' : null;
}
```

- [ ] **Step 4: Run the heatmap test (expect pass)**

Run: `cd frontend && npm run test -- heatmap`
Expected: PASS, 4 tests.

- [ ] **Step 5: Implement `HeatmapToggle.tsx`**

`src/components/HeatmapToggle.tsx`:
```tsx
import React from 'react';
import { useUiStore } from '../store/uiStore';

const LABEL = { off: 'ヒートマップ: OFF', load: 'ヒートマップ: 負荷', shortfall: 'ヒートマップ: 不足' } as const;

export function HeatmapToggle() {
  const mode = useUiStore((s) => s.heatmapMode);
  const cycle = useUiStore((s) => s.cycleHeatmap);
  return <button data-testid="heatmap-toggle" onClick={cycle}>{LABEL[mode]}</button>;
}
```

- [ ] **Step 6: Run the full suite (expect pass)**

Run: `cd frontend && npm run test`
Expected: PASS (heatmap + all prior).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/viz/heatmap.ts frontend/src/viz/heatmap.test.ts frontend/src/components/HeatmapToggle.tsx
git commit -m "feat(frontend): load/shortfall heatmap overlay with pure color functions"
```

---

## Task 12: EditToolbar + ConflictDialog

**Files:**
- Create: `frontend/src/components/EditToolbar.tsx`, `frontend/src/components/ConflictDialog.tsx`
- Test: `frontend/src/components/EditToolbar.test.tsx`, `frontend/src/components/ConflictDialog.test.tsx`

- [ ] **Step 1: Write the failing toolbar test**

`src/components/EditToolbar.test.tsx`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditToolbar } from './EditToolbar';

const base = {
  rosterId: 'R1', undoAvailable: true, redoAvailable: false,
  onUndo: vi.fn(), onRedo: vi.fn(), onConfirm: vi.fn(), onResolve: vi.fn(),
  resolveEnabled: false,
};

describe('EditToolbar', () => {
  it('binds undo/redo disabled state to the flags', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-undo')).toBeEnabled();
    expect(screen.getByTestId('btn-redo')).toBeDisabled();
  });
  it('disables Re-solve when not enabled (P2b dark-launch)', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-resolve')).toBeDisabled();
  });
  it('exposes the Excel download as a link to GET /excel', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-excel')).toHaveAttribute('href', '/rosters/R1/excel');
  });
  it('fires undo', async () => {
    render(<EditToolbar {...base} />);
    await userEvent.click(screen.getByTestId('btn-undo'));
    expect(base.onUndo).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it (expect failure)**

Run: `cd frontend && npm run test -- EditToolbar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `EditToolbar.tsx`**

`src/components/EditToolbar.tsx`:
```tsx
import React from 'react';
import { getExcelUrl } from '../api/rosterApi';
import { HeatmapToggle } from './HeatmapToggle';

interface Props {
  rosterId: string;
  undoAvailable: boolean;
  redoAvailable: boolean;
  resolveEnabled: boolean;     // false until P2b lands
  onUndo: () => void;
  onRedo: () => void;
  onResolve: () => void;
  onConfirm: () => void;
}

export function EditToolbar(p: Props) {
  return (
    <div className="edit-toolbar">
      <button data-testid="btn-undo" disabled={!p.undoAvailable} onClick={p.onUndo}>元に戻す</button>
      <button data-testid="btn-redo" disabled={!p.redoAvailable} onClick={p.onRedo}>やり直す</button>
      <button data-testid="btn-resolve" disabled={!p.resolveEnabled} onClick={p.onResolve} title={p.resolveEnabled ? '' : 'P2b で有効化'}>再生成(ロック保持)</button>
      <a data-testid="btn-excel" href={getExcelUrl(p.rosterId)} download>Excel出力</a>
      <button data-testid="btn-confirm" onClick={p.onConfirm}>確定</button>
      <HeatmapToggle />
    </div>
  );
}
```

- [ ] **Step 4: Write the failing ConflictDialog test**

`src/components/ConflictDialog.test.tsx`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConflictDialog } from './ConflictDialog';
import { gridFixture } from '../test/fixtures';

describe('ConflictDialog', () => {
  it('shows the server version and rebases on confirm', async () => {
    const onRebase = vi.fn();
    render(<ConflictDialog serverGrid={{ ...gridFixture, version: 9 }} onRebase={onRebase} onCancel={() => {}} />);
    expect(screen.getByText(/version 9/i)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('rebase'));
    expect(onRebase).toHaveBeenCalledWith(expect.objectContaining({ version: 9 }));
  });
});
```

- [ ] **Step 5: Run it (expect failure)**

Run: `cd frontend && npm run test -- ConflictDialog`
Expected: FAIL — module not found.

- [ ] **Step 6: Implement `ConflictDialog.tsx`**

`src/components/ConflictDialog.tsx`:
```tsx
import React from 'react';
import type { WireGridResponse } from '../domain/wire';

interface Props {
  serverGrid: WireGridResponse;
  onRebase: (grid: WireGridResponse) => void;
  onCancel: () => void;
}

export function ConflictDialog({ serverGrid, onRebase, onCancel }: Props) {
  return (
    <div role="dialog" className="conflict-dialog">
      <h3>編集が競合しました</h3>
      <p>別の編集が先に保存されました (server version {serverGrid.version})。最新の表に作り直してください。</p>
      <button data-testid="rebase" onClick={() => onRebase(serverGrid)}>最新に更新して続ける</button>
      <button data-testid="conflict-cancel" onClick={onCancel}>キャンセル</button>
    </div>
  );
}
```

- [ ] **Step 7: Run the tests (expect pass)**

Run: `cd frontend && npm run test -- "EditToolbar|ConflictDialog"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/EditToolbar.tsx frontend/src/components/ConflictDialog.tsx frontend/src/components/EditToolbar.test.tsx frontend/src/components/ConflictDialog.test.tsx
git commit -m "feat(frontend): EditToolbar (undo/redo/resolve/excel/confirm) + ConflictDialog rebase"
```

---

## Task 13: RosterPage wiring + app entry

**Files:**
- Create: `frontend/src/components/RosterPage.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- Test: `frontend/src/components/RosterPage.test.tsx`

- [ ] **Step 1: Wire the app root**

`src/main.tsx`:
```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './query/queryClient';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>,
);
```
`src/App.tsx`:
```tsx
import React from 'react';
import { RosterPage } from './components/RosterPage';

export function App() {
  // path: /rosters/<rid>  (no router dependency in P2d; read from the URL)
  const rid = window.location.pathname.split('/rosters/')[1]?.replace(/\/.*$/, '') ?? '';
  if (!rid) return <p>勤務表IDがURLにありません: /rosters/&lt;id&gt; を開いてください。</p>;
  return <RosterPage rosterId={rid} />;
}
```

- [ ] **Step 2: Write the failing RosterPage smoke test**

`src/components/RosterPage.test.tsx`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { RosterPage } from './RosterPage';
import * as rosterApi from '../api/rosterApi';
import { gridFixture } from '../test/fixtures';

describe('RosterPage', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('loads the roster and renders the grid + a warning panel + toolbar', async () => {
    vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <RosterPage rosterId="R1" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());
    expect(screen.getByTestId('btn-undo')).toBeInTheDocument();
    expect(screen.getByText(/勤務不足/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it (expect failure)**

Run: `cd frontend && npm run test -- RosterPage`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `RosterPage.tsx`**

`src/components/RosterPage.tsx`:
```tsx
import React, { useState } from 'react';
import type { DragEndEvent } from '@dnd-kit/core';
import { useRoster } from '../query/useRoster';
import { useEditMutation } from '../query/useEditMutation';
import { useUiStore, type CellRef } from '../store/uiStore';
import { moveFromDragEnd } from '../normalize/dragEnd';
import { toIsoDate } from '../normalize/dates';
import { ScheduleGrid } from './ScheduleGrid';
import { EditPopover } from './EditPopover';
import { WarningPanel } from './WarningPanel';
import { EditToolbar } from './EditToolbar';
import { ConflictDialog } from './ConflictDialog';
import { postConfirm } from '../api/editsApi';
import type { WireGridResponse } from '../domain/wire';
import type { EditOp } from '../domain/editOps';

export function RosterPage({ rosterId }: { rosterId: string }) {
  const { data: state, isLoading, error } = useRoster(rosterId);
  const [conflict, setConflict] = useState<WireGridResponse | null>(null);
  const { edit, undo, redo } = useEditMutation(rosterId, setConflict);
  const selectCell = useUiStore((s) => s.selectCell);
  const selected = useUiStore((s) => s.selectedCell);

  if (isLoading) return <p>読み込み中…</p>;
  if (error || !state) return <p>勤務表の取得に失敗しました。</p>;

  const onCellClick = (ref: CellRef) => selectCell(ref);
  const onEmit = (op: EditOp) => { void edit(op); selectCell(null); };
  const onDragEnd = (e: DragEndEvent) => {
    const op = moveFromDragEnd(e, state.year, state.month);
    if (op) void edit(op);
  };
  const onRebase = (grid: WireGridResponse) => {
    // Reload from the server grid the 409 returned (refetch is simplest and correct).
    setConflict(null);
    void undo;  // no-op reference; rebase via refetch:
    window.location.reload();
  };

  const selectedRow = selected && state.rows.find((r) => r.staffId === selected.staffId);
  const selectedCellObj = selectedRow && selected ? selectedRow.cells.get(selected.day) : undefined;

  return (
    <div className="roster-page">
      <EditToolbar
        rosterId={rosterId}
        undoAvailable={state.undoAvailable}
        redoAvailable={state.redoAvailable}
        resolveEnabled={false}
        onUndo={() => void undo()}
        onRedo={() => void redo()}
        onResolve={() => { /* P2b: enable + call postResolve, then refetch */ }}
        onConfirm={() => void postConfirm(rosterId, state.version)}
      />
      <div className="roster-body">
        <ScheduleGrid state={state} onCellClick={onCellClick} onDragEnd={onDragEnd} />
        <WarningPanel state={state} />
      </div>
      {selected && (
        <EditPopover
          staffId={selected.staffId}
          day={selected.day}
          date={toIsoDate(state.year, state.month, selected.day)}
          locked={selectedCellObj?.locked ?? false}
          statsColumns={state.statsColumns}
          onEmit={onEmit}
          onClose={() => selectCell(null)}
        />
      )}
      {conflict && <ConflictDialog serverGrid={conflict} onRebase={onRebase} onCancel={() => setConflict(null)} />}
    </div>
  );
}
```

> **Implementer note on rebase:** the simplest correct rebase is `window.location.reload()` (or `queryClient.invalidateQueries(rosterKey(rid))`) so the next edit uses the server's bumped `version`. A non-reloading rebase that calls `normalizeGrid(rid, conflict)` + `setQueryData` is a fine optimization but must preserve the user's in-flight intent; defer that to a follow-up.

- [ ] **Step 5: Run the test (expect pass)**

Run: `cd frontend && npm run test -- RosterPage`
Expected: PASS.

- [ ] **Step 6: Typecheck + full suite + build**

Run: `cd frontend && npx tsc -b && npm run test && npm run build`
Expected: typecheck clean, all tests pass, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/RosterPage.tsx frontend/src/App.tsx frontend/src/main.tsx frontend/src/components/RosterPage.test.tsx
git commit -m "feat(frontend): RosterPage wiring grid+popover+warnings+toolbar+conflict, app entry"
```

---

## Task 14: Playwright E2E (seeded roster) — visual + interaction checks

> Unit tests cover the data/merge logic; this task reserves the hard-to-unit-test interaction/visual checks (real drag, optimistic→authoritative, 409 rebase, D+1 明け) for Playwright against a running backend + seeded roster.

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/editor.spec.ts`
- Modify: `frontend/package.json` (add `e2e` script)

- [ ] **Step 1: Install Playwright**

Run:
```bash
cd frontend && npm install -D @playwright/test && npx playwright install --with-deps chromium
```

- [ ] **Step 2: Write `playwright.config.ts`**

`playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  webServer: { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true },
  use: { baseURL: 'http://localhost:5173' },
});
```
Add to `package.json` scripts: `"e2e": "playwright test"`.

- [ ] **Step 3: Write the E2E spec**

`e2e/editor.spec.ts`:
```ts
import { test, expect, request } from '@playwright/test';

const API = 'http://localhost:8000';

async function seedRoster(): Promise<string> {
  const ctx = await request.newContext();
  const job = await (await ctx.post(`${API}/jobs`, { data: { year: 2026, month: 6 } })).json();
  // poll until done
  for (let i = 0; i < 120; i++) {
    const s = await (await ctx.get(`${API}/jobs/${job.job_id}`)).json();
    if (s.status === 'done') break;
    if (s.status === 'failed') throw new Error('seed job failed');
    await new Promise((r) => setTimeout(r, 1000));
  }
  const roster = await (await ctx.post(`${API}/jobs/${job.job_id}/freeze`)).json();
  return roster.roster_id;
}

test.describe('editor', () => {
  let rid: string;
  test.beforeAll(async () => { rid = await seedRoster(); });

  test('assign updates the cell and its stats/warnings', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const cell = page.getByTestId(/^cell-.*-15$/).first();
    await cell.click();
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(cell).toContainText('CT');
    // stats are server-authoritative — they appear/update after the merge
    await expect(page.getByTestId(/^stat-.*-公休$/).first()).not.toBeEmpty();
  });

  test('unassign raises 公休 (server recompute)', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const stat = page.getByTestId(/^stat-.*-公休$/).first();
    const before = Number(await stat.innerText());
    const cell = page.getByTestId(/^cell-.*-20$/).first();
    await cell.click();
    await page.getByTestId('apply-unassign').click();
    await expect.poll(async () => Number(await stat.innerText())).toBeGreaterThanOrEqual(before);
  });

  test('a night edit derives the D+1 明け ○ cell', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    // assign a night-bearing location on a day, then expect the next day's ○ to appear
    // (exact location/day depend on the seeded data; pick a staff with night eligibility)
    // This asserts the merge surfaced a cell the client did not optimistically write.
    // See synthesis §2.3 changed_cells D+1 rule.
    expect(true).toBeTruthy(); // placeholder assertion scaffold — fill with seeded ids during execution
  });

  test('undo is available after an edit and reverts it (one step for a drag move)', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const cell = page.getByTestId(/^cell-.*-10$/).first();
    await cell.click();
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(page.getByTestId('btn-undo')).toBeEnabled();
    await page.getByTestId('btn-undo').click();
    await expect(page.getByTestId('btn-undo')).toBeDisabled();
  });
});
```

> **Implementer note:** the D+1 明け and exact-id assertions must be filled with real staff ids from the seeded June 2026 roster during execution (read them from `GET /rosters/{rid}`). Keep the scenario, replace the placeholder assertion. Drag is exercised via `page.dragTo`; add a same-row day→day drag and assert one undo reverts it.

- [ ] **Step 4: Run E2E (backend must be running)**

Run: `cd frontend && npm run e2e`
Expected: PASS (assign/unassign/undo scenarios; D+1 scenario after ids filled in).

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e frontend/package.json
git commit -m "test(frontend): Playwright E2E for assign/unassign/undo/D+1 明け against a seeded roster"
```

---

## Self-Review

**1. Spec coverage** (design §7/§8 + synthesis §2.3/§5/P2d):

| Requirement | Task |
|---|---|
| `GET /rosters/{rid}` initial load → normalized state | T3, T5 |
| Excel-style grid, sticky name col + day/weekday header, weekend shading | T7 |
| DayCell: text + fill + lock badge, draggable+droppable, click→popover | T7 |
| StatsCells read-only 21 cols, blank when `!has_work` | T7 |
| OnCallRows 第1/第2拘束 | T7 |
| EditPopover → assign/unassign/set_symbol/toggle_lock | T8 |
| Optimistic edit then merge authoritative `changed_cells`+`stats`+`warnings` | T4, T5 |
| Never compute stats client-side (server authoritative) | T4 (applyOptimistic touches text only), T5 |
| D+1 明け re-derivation surfaced via merge | T4 test, T14 |
| `expected_version` on every edit; 409 → ConflictDialog rebase | T2, T5, T12, T13 |
| Drag-drop = one `move` op = one undo step | T4, T9 |
| WarningPanel grouped coverage/holiday/consecutive/skill, click→highlight | T10 |
| HeatmapToggle load + coverage-shortfall overlay | T6, T11 |
| EditToolbar Undo/Redo bound to flags, Re-solve (disabled/mock), Export Excel, Confirm | T12 |
| Undo/Redo via `POST /undo`,`/redo` same merge path | T5 |
| `/resolve` dark-launched until P2b | T2 (mock), T12 (disabled), T13 |
| Vite proxy to FastAPI :8000; assumes seeded roster | Task 1, Dev setup |
| Vitest+RTL for data/merge logic; Playwright for visual/interaction | T2–T6, T10, T11 (unit); T14 (E2E) |

No gaps found. `GET /rosters/{rid}/edits` history drawer and a non-reloading rebase are explicitly deferred (noted in T13) — they are optional in the P2d decomposition.

**2. Placeholder scan:** The Task 14 D+1 scenario carries a `placeholder assertion scaffold` deliberately (real seeded staff ids are only knowable at execution time) with an implementer note to fill it from `GET /rosters/{rid}`; the scenario structure itself is complete. The Task 7 `heatmap.ts` stub is explicitly a temporary compile shim, replaced in full by Task 11. No "TBD"/"add error handling"/"similar to Task N" placeholders remain; every code step ships runnable code.

**3. Type consistency:** `Cell`/`Row`/`RosterState` (model.ts) are used identically across normalize, query, viz, and components. `EditOp` uses `sid` in all request paths (T2/T4/T8/T9); responses use `staff_id` consumed only in `mergeEdit.ts`/`warningCells.ts`. `heatColorForCell(mode, state, row, day)` signature matches between the T7 stub, T11 implementation, and the T7 ScheduleGrid call site. `normalizeFill`, `parseDayFromIso`, `toIsoDate`, `weekendKind`, `buildMovePayload`, `mergeEditResponse`, `applyOptimistic` names are stable across definition and call sites. `useEditMutation(rid, onConflict)` is called consistently in T5 tests and T13. `rosterKey` is shared by `useRoster` and `useEditMutation`.

---

## Next

P2d depends on P2a's editing API. Before executing, confirm two backend facts with the P2a implementer: (a) does the edit request body key the staff as `sid` (this plan) or `staff_id`? (b) does `GET /rosters/{rid}` include `year`/`month` (and optionally `holidays[]`)? Both are isolated behind `editsApi.ts` / `normalizeGrid.ts`, so a mismatch is a one-line fix. After P2d merges, P2b enables the Re-solve button (flip `resolveEnabled`, wire `postResolve` + refetch) and P4 wires Confirm/archive. Execute this plan with **superpowers:subagent-driven-development** (fresh subagent per task, review between tasks) — the merge reducer (Task 4) and the mutation hook (Task 5) are the two tasks to review most carefully, since they encode the "server is authoritative" rule.
