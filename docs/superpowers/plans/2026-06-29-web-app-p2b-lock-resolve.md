# Web App P2b — Partial-Lock Re-Solve (lock hooks + lock-aware post-processors + `/resolve`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Implement **strictly in order** — the empty-lock byte-identity gate (Task 1) must be green before any injection code is written.

> **User directive (verbatim):** 「コスト度外視構いませんので最高の成果を出せるように可能な限り継続して」 — cost is not a concern; keep going to produce the best possible result. Favor faithfulness/determinism over shortcuts.

**Goal:** Re-run the solver while holding `locked=1` roster cells fixed, **without changing weights / objective / seed / `num_workers` / deterministic-time stops**, so determinism is preserved. The keystone guarantee is: with an **empty** lock set, `run_schedule(..., locked_assignments={})` produces output **byte-identical** to today's `run_schedule(...)`. On top of that, a forced cell appears in the output, a forbidden cell is excluded, locked cells survive every post-processor, a conflicting lock is reported as the exact offending cells (not a silent degraded day), and a `POST /rosters/{rid}/resolve` endpoint re-solves under the existing solve serialization, re-freezes (keep locked rows / replace unlocked), and records a synthetic undoable `op='resolve'` edit.

**Architecture:**
- **Lock-set shape (single structure threaded to both schedulers):**
  ```python
  locked_assignments: dict[datetime.date, {
      'force':  set[tuple[str, str]],   # {(staff_id, loc_code)}  — loc_code '夜' = night-domain
      'forbid': set[tuple[str, str]],   # {(staff_id, loc_code)}
  }]
  ```
  Day-domain entries use a real day `loc_code` (incl. `'休'`/`'○'` = OFF-lock). Night-domain entries use `loc_code == '夜'`. The **day** injection ignores `'夜'` entries; the **night** injection acts **only** on `'夜'` entries. In P2b the `/resolve` builder emits **day-domain locks only** (toggle_lock targets `kind='day'` rows), so the night model sees an empty lock set and re-solves freely. Keys are `datetime.date`; persistence is ISO `YYYY-MM-DD`, converted at the boundary.
- **Enforcement mechanism = CP-SAT assumptions, not bare `model.Add`.** Each lock is registered as an assumption literal (`model.AddAssumption(lit)`); when feasible the assumption *is* a hard constraint, and on `INFEASIBLE` `solver.SufficientAssumptionsForInfeasibility()` returns exactly the conflicting literals → mapped back to `(staff_id, loc_code, date, mode)`. This is the one mechanism that both **enforces** and **diagnoses**; mixing `model.Add` + assumption would make infeasibility un-attributable (the `Add` alone makes the model infeasible, so the assumption subset comes back empty). With an **empty** lock set, **zero** `AddAssumption` calls happen → the model, presolve, search, and solution are unchanged → byte-identical. (See "Determinism contract" below.)
- **Threading:** `run_schedule(*, locked_assignments=None)` → `DayScheduler(..., locked_assignments=...)` stored on `self`, injected in `_schedule_one_day` immediately **before** `model.Maximize` (`day_scheduler.py:1229`), after all vars/constraints → `NightScheduler.schedule(..., locked_assignments=...)` injected **after** `_add_soft_constraints` (`night_scheduler.py:63`) and **before** `CpSolver()` (`:67`).
- **Post-processor lock-awareness (BIGGEST RISK):** `rebalance_workload` (`main.py:512`), `optimize_assignments_cpsat` (`main.py:754`), `assign_monthly_off_days` (`main.py:19`) run *after* the day solve and will move locked cells unless made lock-aware. Each gains `locked_assignments=None`; when empty/None they are byte-identical to today (gate preserved). When non-empty, a shared **`reassert_locks(...)` safety net** runs after each helper to guarantee every locked `(staff_id, date)` keeps exactly its locked location (in-model pinning in the CP-SAT optimizer is an additional optimization, not the load-bearing guarantee).
- **Diagnostics:** (1) a pure, fast `validate_lock_set(...)` pre-check (≤1 forced loc per staff/day, forced count per (loc,day) ≤ needs/capacity); (2) assumption-based `lock_conflicts` from the solver for hard-constraint collisions. Pruned-var forces (a `(sid,loc)` with no BoolVar) are collected as `unlockable_locks` (reported, never swallowed).
- **`/resolve`:** `resolve_roster(conn, rid, *, runner, user_id=None)` in `webapp/api/rosters.py` reads `locked=1` day rows → builds `locked_assignments` → re-solves under `jobs._solve_lock` (seed=42, num_workers=1) → if `lock_conflicts` → `422` with offending cells → else re-freeze (keep locked rows, replace unlocked) → append `op='resolve'` edit (full-row before/after snapshot, undoable) → bump `version` → return grid + warnings + `unlockable` + version.

**Tech Stack:** Python 3.13, OR-Tools CP-SAT (`ortools.sat.python.cp_model`), FastAPI + Starlette `TestClient`, stdlib `sqlite3`, pytest with `tmp_path` temp DBs. Real-solver tests are slow (~2 min/run) and marked `@pytest.mark.slow`; lock-set pre-validation and `/resolve` wiring tests are **fast** (monkeypatch `RUNNER` with a canned `ScheduleResult`; never invoke the real solver).

**Scope note:** P2b is the **partial-lock re-solve only**. NO new UI (the React Re-solve button is P2d, dark-launched against this endpoint). NO night-cell locking from the UI (toggle_lock writes only `kind='day'` rows; the night-domain `'夜'` lock path is implemented and unit-tested but unused by `/resolve` in v1). NO master CRUD (P3). NO change to the day/night objective, weights, seed, worker count, or deterministic-time stops. The `skill`/power-balance warning group stays a P3 placeholder.

**Provenance (from the P2 Technical Design synthesis §4 "Partial-lock re-solve", the `scheduler-lock` map reader, and design spec §7 "部分ロック→再生成" / §11-8 / §14):**
- Lock-set shape + injection points: synthesis §4.1–§4.2; map reader §2. Day vars pruned (`day_scheduler.py:719,786`), inject-before-Maximize (`:1229`), extract (`:1256`). Night vars dense (`night_scheduler.py:54-56`), inject-before-CpSolver (`:67`), minimize (`:498`), role permute post-solve (`:500-557`) ⇒ **night role cannot be forced, only occupancy**.
- Pruned-var gotcha: synthesis §4.3 / map §2-day + §4. `if (sid,lc) in x:` else report.
- Post-processor risk: synthesis §4.3 ("biggest integration risk") / map §3-4. Threaded helpers at `main.py:1175,1180,1185`.
- Infeasibility hard constraints — Day: one-loc `sum(vars_s)<=1` (`:999`), headcount caps (`:1291,:1467`), `Add(==0)` zones (`:983,:993,:1043,:1112,:1350,:1359,:1173-1174`). Night: exact capacity `==max(3,yaki)` (`:105`), no-consec 2-window (`:119`), prev-month boundary (`:131`), skill coverage `>=1` (`:247-249`), symbol bans (`:189`), distribution caps (`:421,:449`). (synthesis §4.4 / map §4.)
- Assumptions + `SufficientAssumptionsForInfeasibility`: synthesis §4.4 mitigation (2) / map §4.
- `/resolve` + re-freeze + synthetic `op='resolve'` edit + `_solve_lock`: synthesis §2.3, §4.4 last paragraph; spec §7.
- Determinism guardrails (`seed=42`, `num_workers=1`, deterministic-time): spec §3.2, §11 final line; `day_scheduler.py:1236-1239`, `night_scheduler.py:71-75`.

**Treat as already existing (do NOT re-implement):**
- `run_schedule(year, month, data_dir="shift_scheduler/data", output_dir=None, *, target_holidays=None) -> ScheduleResult` at `main.py:1119-1280`. **Has no `locked_assignments` param yet** — Task 1 adds it.
- `ScheduleResult` (`shift_scheduler/src/models/schedule_result.py`): `as_dict()` (`:21-43`) lists keys **explicitly** and already excludes `workbook_bytes` and `daily_location_needs`. Any new lock field MUST follow that pattern (excluded from `as_dict()`), or the golden gate breaks.
- P2a-2 persistence: `webapp/api/db.py` (4 tables; `roster_edits.op` CHECK **already includes `'resolve'`**), `webapp/api/rosters.py` (`freeze_roster`, `roster_to_dicts` → returns `locked={(sid,day):True}` for `kind='day'` rows; `_locked_cells`, `build_roster_grid`, `roster_warnings`, `apply_edit`, `undo`, `redo`, `_restore_rows`, `_recompute_and_persist`, `ConcurrencyError`, `_now/_iso/_day_of`), `webapp/api/main.py` (endpoints + `RUNNER = run_schedule` indirection + `get_db` dependency).
- `webapp/api/jobs.py:44` `_solve_lock = threading.Lock()` — reuse to serialize the re-solve.
- `shift_scheduler/src/grid_derivation.build_grid` and `shift_scheduler/src/stats_engine.recompute_stats(day_assignments, night_assignments, requests, technicians, year, month, target_holidays, *, daily_location_needs=None, staff_scope=None)` — pure, solver-free (P2a-1/2a-2).
- `tests/test_parity_golden.py` + `tests/golden/2026-06_assignments.json` — the parity gate this plan reuses.

---

## Determinism contract (the load-bearing invariant — read before coding)

The single most important property: **`AddAssumption` (and every other lock code path) must be a strict no-op when the lock set is empty.** Concretely:
- `run_schedule(..., locked_assignments=None)` and `locked_assignments={}` MUST behave identically to today.
- In `_schedule_one_day`, `locks = self.locked_assignments.get(current_date, {})`; if `locks` is `{}` (or its `force`/`forbid` sets are empty), the injection loop bodies execute **zero** model mutations and **zero** `AddAssumption` calls.
- Same for the night injection (`locked_assignments or {}` → empty → zero calls).
- The three post-processors, when `locked_assignments` is `None`/empty, take an early path that does **not** call `reassert_locks` and does **not** alter their existing logic.
- Do **not** change `max_deterministic_time`, `max_time_in_seconds`, `random_seed`, `num_workers`, or `log_search_progress` anywhere.

Task 1 proves this with the slow byte-identity gate **before any injection logic exists**, then every subsequent task re-runs that gate to prove it still holds.

---

## Design decisions resolved (ambiguities the synthesis left open)

1. **Assumptions, not bare `Add`, as the enforcement mechanism** (see Architecture). Rationale: one mechanism that both enforces and is diagnosable via `SufficientAssumptionsForInfeasibility()`; empty lock ⇒ zero assumptions ⇒ byte-identical. The synthesis §4.2 sketch used `model.Add(==1/==0)`; this plan upgrades to assumptions because §4.4 requires actionable infeasibility reporting and the two cannot coexist on the same constraint.
2. **OFF-lock reification.** `'休'`/`'○'` are literal `location_code`s with no BoolVar. A force of `(sid,'休')`/`(sid,'○')` means "lock this staff OFF for the day": build `vars_s = [x[sid,l.code] for l in target_locations if (sid,l.code) in x]`; if non-empty, `aux = model.NewBoolVar(...); model.Add(sum(vars_s)==0).OnlyEnforceIf(aux); model.AddAssumption(aux)` (mirrors the `vars_s` pattern at `day_scheduler.py:997`). If `vars_s` is empty the staff already has no work var that day (already effectively off) → no-op (not an error). The `aux` literal carries the conflict mapping for diagnostics.
3. **Night = occupancy only.** Night force/forbid act on `(sid, date)` occupancy; **role (MR/アンギオ/心カテ) cannot be forced** (derived by post-solve permutation, `night_scheduler.py:500-557`). The `'夜'` `loc_code` disambiguates night-domain entries. Documented; not exercised by `/resolve` v1.
4. **Lock surfacing without breaking `as_dict()`.** `ScheduleResult` gains `unlockable_locks: list = field(default_factory=list)` and `lock_conflicts: list = field(default_factory=list)`, **both excluded from `as_dict()`** (mirroring `daily_location_needs`). `/resolve` reads them off the object directly. The golden gate compares `as_dict()`, so the gate is unaffected.
5. **Post-processor guarantee = `reassert_locks` safety net.** A shared helper guarantees lock survival regardless of post-processor internals (`rebalance` greedy swaps; `optimize` CP-SAT accept/reject; `assign_monthly_off_days` blank→休). In-model pinning inside `optimize_assignments_cpsat` is added as an optimization but the **test asserts against the reassert guarantee**. `reassert_locks` only repositions the locked staff's own `(sid,date)` rows (removes the locked staff from any non-locked location that day, ensures the locked location present); it does not evict other staff. Over/under-capacity that results is surfaced by the live `recompute_stats` coverage warnings (the editor's authority > solver, per spec §7).
6. **`/resolve` re-freeze granularity.** Locking is per `kind='day'` cell. Re-solve re-runs everything; on re-freeze: **keep** locked `kind='day'` rows verbatim; **delete + replace** all unlocked rows (day/night/oncall/request) from the new `ScheduleResult`. Known v1 limitation (documented inline): because night re-solves freely, a re-solved night the day *before* a locked day cell makes that cell render `'○'` (明け derivation overrides, `excel_generator.py:252-255`). Acceptable for v1; a future night-lock extension closes it.
7. **`/resolve` undo semantics.** The synthetic `op='resolve'` edit stores **full-row snapshots** of the entire roster's `roster_assignments` in `before_json`/`after_json`, so a single undo restores the complete pre-resolve grid (op-agnostic, reuses `_restore_rows`). `cells` for restore = union of every `(sid, day)` appearing in either snapshot.
8. **Pre-validation vs. solver diagnostics are complementary.** `validate_lock_set` (fast, pure) catches the structural impossibilities cheaply and returns a clear message; the assumption-based `lock_conflicts` (slow, in-solver) catches the genuinely hard-constraint collisions that need the model. `/resolve` runs pre-validation first (422 on structural failure, no solve) then the solve (422 on `lock_conflicts`).

---

## File Structure

**Create:**
- `tests/test_lock_resolve.py` — slow gate + slow force/forbid/conflict/post-processor tests + fast pre-validation + fast `/resolve` wiring tests.
- `shift_scheduler/src/lock_utils.py` — pure helpers shared by schedulers, post-processors, and `/resolve`: `validate_lock_set(...)`, `reassert_locks(...)`, `day_locks_from_rows(...)` (rows → `locked_assignments`), and the `'夜'`/OFF-lock constants. (Pure, no solver, fast-unit-testable.)

**Modify:**
- `main.py` — `run_schedule` signature `+ *, locked_assignments=None`; pass to `DayScheduler(...)` (`:1169`) and `NightScheduler.schedule(...)` (`:1153`); thread into `rebalance_workload`/`optimize_assignments_cpsat`/`assign_monthly_off_days` (`:1175,:1180,:1185`) + `reassert_locks` after each; collect `unlockable_locks`/`lock_conflicts` from the day scheduler into the returned `ScheduleResult`.
- `shift_scheduler/src/models/schedule_result.py` — add `unlockable_locks` / `lock_conflicts` fields (excluded from `as_dict()`).
- `shift_scheduler/src/schedulers/day_scheduler.py` — `__init__` stores `self.locked_assignments`, `self.unlockable_locks`, `self.lock_conflicts`; injection block before `:1229`; conflict extraction after `solver.Solve`.
- `shift_scheduler/src/schedulers/night_scheduler.py` — `schedule(..., locked_assignments=None)`; `'夜'`-only injection between `:63` and `:67`.
- `main.py` `rebalance_workload` / `optimize_assignments_cpsat` / `assign_monthly_off_days` — `locked_assignments=None` params + lock-awareness.
- `webapp/api/rosters.py` — `resolve_roster(...)`, `LockConflictError`, `_resolve_rows_from_result(...)`, `day_locks_from_rows` wiring.
- `webapp/api/main.py` — `POST /rosters/{rid}/resolve` endpoint.

All commands assume repo root `"/Users/kohei/Desktop/local-shift ver1"` is cwd with the venv active (`source .venv/bin/activate`). Run tests with `python -m pytest`. Fast tests: `python -m pytest -m "not slow"`. The full slow gate: `python -m pytest tests/test_lock_resolve.py -m slow` (and the existing `tests/test_parity_golden.py -m slow`).

---

## Task 1 — Empty-lock byte-identity gate (establish FIRST, before any injection logic)

**Goal:** Add the `locked_assignments` keyword to `run_schedule` (threaded but *inert* — no injection code yet) and the inert lock fields to `ScheduleResult`, and prove that an empty/None lock set changes nothing. This is the single most important test in the plan.

- [ ] **Step 1 (RED).** Create `tests/test_lock_resolve.py` with the gate:
  ```python
  # tests/test_lock_resolve.py
  import json
  import os
  import pytest
  from main import run_schedule

  DATA_DIR = "shift_scheduler/data"
  GOLDEN = "tests/golden/2026-06_assignments.json"

  def _canon(d):
      return json.loads(json.dumps(d, ensure_ascii=False, sort_keys=True))

  @pytest.mark.slow
  def test_empty_lock_set_is_byte_identical_to_today_and_golden():
      base = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
      empty = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments={}).as_dict()
      none_ = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=None).as_dict()
      assert _canon(empty) == _canon(base)
      assert _canon(none_) == _canon(base)
      assert os.path.exists(GOLDEN), "golden snapshot missing"
      with open(GOLDEN, encoding="utf-8") as f:
          expected = json.load(f)
      assert _canon(empty) == _canon(expected)

  @pytest.mark.slow
  def test_empty_lock_does_not_leak_lock_fields_into_as_dict():
      d = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments={}).as_dict()
      assert "unlockable_locks" not in d and "lock_conflicts" not in d
  ```
  Run `python -m pytest tests/test_lock_resolve.py -m slow` — expect failure (`run_schedule` rejects `locked_assignments`).

- [ ] **Step 2 (GREEN).** In `shift_scheduler/src/models/schedule_result.py`, add after `daily_location_needs` (`:19`):
  ```python
      unlockable_locks: list = field(default_factory=list)  # forces with no var (reported)
      lock_conflicts: list = field(default_factory=list)    # assumption-infeasibility cells
  ```
  Do **not** add them to `as_dict()` (`:21-43`) — they must stay excluded like `daily_location_needs`.

- [ ] **Step 3 (GREEN).** In `main.py`, change the `run_schedule` signature (`:1119-1120`) to:
  ```python
  def run_schedule(year: int, month: int, data_dir: str = "shift_scheduler/data",
                   output_dir: str | None = None, *, target_holidays: int | None = None,
                   locked_assignments: dict | None = None) -> ScheduleResult:
  ```
  Add **inert** wiring only (no injection yet): pass `locked_assignments=locked_assignments` into the `DayScheduler(...)` constructor (`:1169-1173`) and `night_scheduler.schedule(requests, night_counts, prev_night_history, locked_assignments=locked_assignments)` (`:1153`). In the returned `ScheduleResult(...)` (`:1269`), add `unlockable_locks=getattr(day_scheduler, "unlockable_locks", []), lock_conflicts=getattr(day_scheduler, "lock_conflicts", [])`.

- [ ] **Step 4 (GREEN).** In `day_scheduler.py.__init__` (`:18-29`), accept and store the param (still unused):
  ```python
                 disable_training: bool = False, target_holidays: int = 9,
                 locked_assignments: dict | None = None):
      ...
      self.locked_assignments = locked_assignments or {}
      self.unlockable_locks = []
      self.lock_conflicts = []
  ```
  In `night_scheduler.py.schedule` (`:27`), add the trailing param `locked_assignments: dict | None = None` and **do not** reference it yet.

- [ ] **Step 5 (GREEN).** Run `python -m pytest tests/test_lock_resolve.py -m slow tests/test_parity_golden.py -m slow`. Both gate tests + the existing parity test must pass. **Do not proceed until green.**

- [ ] **Commit:** `feat(p2b): thread inert locked_assignments through run_schedule; empty-lock byte-identity gate green`

---

## Task 2 — `lock_utils` pure helpers + pre-validation (fast, no solver)

**Goal:** Land the pure, solver-free helpers and the structural pre-validator so later tasks (and `/resolve`) can build/validate lock sets cheaply.

- [ ] **Step 1 (RED).** Add fast tests to `tests/test_lock_resolve.py`:
  ```python
  from datetime import date
  from shift_scheduler.src.lock_utils import (
      validate_lock_set, reassert_locks, day_locks_from_rows, NIGHT_LOC, OFF_LOCS,
  )

  def test_validate_rejects_two_forced_locs_same_staff_day():
      la = {date(2026, 6, 10): {"force": {("T013", "CT"), ("T013", "病CT")}, "forbid": set()}}
      errs = validate_lock_set(la, daily_location_needs={})
      assert any("T013" in e and "2026-06-10" in e for e in errs)

  def test_validate_rejects_forced_count_over_needs():
      la = {date(2026, 6, 10): {"force": {("T001", "MG"), ("T002", "MG")}, "forbid": set()}}
      needs = {10: {"MG": 1}}
      errs = validate_lock_set(la, daily_location_needs=needs)
      assert any("MG" in e for e in errs)

  def test_validate_allows_off_lock_and_single_force():
      la = {date(2026, 6, 10): {"force": {("T013", "CT"), ("T020", "休")}, "forbid": set()}}
      assert validate_lock_set(la, daily_location_needs={10: {"CT": 3}}) == []

  def test_day_locks_from_rows_builds_force_for_work_and_off():
      rows = [
          {"staff_id": "T013", "date": "2026-06-10", "kind": "day",
           "location_or_role": "CT", "locked": 1},
          {"staff_id": "T020", "date": "2026-06-10", "kind": "day",
           "location_or_role": None, "locked": 1},   # empty-cell sentinel = OFF
          {"staff_id": "T099", "date": "2026-06-10", "kind": "day",
           "location_or_role": "MG", "locked": 0},    # not locked -> ignored
      ]
      la = day_locks_from_rows(rows)
      d = date(2026, 6, 10)
      assert ("T013", "CT") in la[d]["force"]
      assert ("T020", "休") in la[d]["force"]
      assert all(sid != "T099" for sid, _ in la[d]["force"])

  def test_reassert_locks_repositions_locked_staff(monkeypatch):
      from shift_scheduler.src.models.assignment import DayAssignment
      from shift_scheduler.src.models.skill import SkillRank
      d = date(2026, 6, 10)
      rows = [DayAssignment(date=d, staff_id="T013", location_code="MG", rank=SkillRank.B)]
      la = {d: {"force": {("T013", "CT")}, "forbid": set()}}
      out = reassert_locks(rows, la, 2026, 6)
      cells = {(a.staff_id, a.location_code) for a in out if a.date == d}
      assert ("T013", "CT") in cells and ("T013", "MG") not in cells
  ```
  Run `python -m pytest tests/test_lock_resolve.py -m "not slow"` — expect import/collection failure.

- [ ] **Step 2 (GREEN).** Create `shift_scheduler/src/lock_utils.py`:
  - `NIGHT_LOC = '夜'`; `OFF_LOCS = {'休', '○'}`.
  - `day_locks_from_rows(rows) -> dict[date, {'force': set, 'forbid': set}]`: for each row with `kind=='day'` and `locked` truthy, parse `date.fromisoformat(row['date'])`; if `location_or_role` in real-work → add `(sid, loc)` to `force`; if `location_or_role` is `None` (empty-cell sentinel) or in `OFF_LOCS` → add `(sid, '休')` to `force` (OFF-lock). Skip `'夜'` here (night not UI-lockable in v1). Returns `{}`-defaulted structure.
  - `validate_lock_set(locked_assignments, daily_location_needs) -> list[str]`: pure structural checks, **no solver**:
    - ≤1 **work** force per `(staff, date)` (OFF-lock `'休'` counts as the staff's single force; a work force + an OFF force for the same staff/day is a contradiction → error).
    - per `(date, loc)` where `loc` not in `OFF_LOCS|{NIGHT_LOC}` and not parenthesized (`startswith('(') and endswith(')')`): `#forced ≤ daily_location_needs.get(day,{}).get(loc, ∞)` (skip the cap when needs unknown for that loc).
    - a `(sid, loc)` in both `force` and `forbid` for the same date → error.
    - ISO-format the date in every message; return `[]` when clean.
  - `reassert_locks(day_result_list, locked_assignments, year, month) -> list[DayAssignment]`: for each locked `(sid, loc)` force on date `d`: drop every `DayAssignment` with that `(sid, d)`; if `loc not in OFF_LOCS`, append `DayAssignment(date=d, staff_id=sid, location_code=loc, rank=skills-agnostic NONE-or-preserved)`; if `loc in OFF_LOCS`, append the literal `'休'` row (mirrors `assign_monthly_off_days` blank→休). Preserve all non-locked rows untouched. (Rank: look up via a passed `skills` map if available, else `SkillRank.NONE`; for v1 reassert is a safety net so `NONE` is acceptable — note inline that the subsequent `recompute_stats` does not depend on rank.)

- [ ] **Step 3 (GREEN).** Run `python -m pytest tests/test_lock_resolve.py -m "not slow"` — green.

- [ ] **Commit:** `feat(p2b): pure lock_utils (validate_lock_set / reassert_locks / day_locks_from_rows)`

---

## Task 3 — Day-scheduler lock injection (force / forbid / OFF) via assumptions

**Goal:** Make a forced cell appear and a forbidden cell disappear in `run_schedule` output, while keeping the empty-lock gate green. Pruned-var forces are reported (Task 4).

- [ ] **Step 1 (RED).** Add slow tests (pick a staff/date/location that is feasible and not normally chosen — read the golden to choose a concrete `(staff_id, loc, day)` that is currently *unassigned* but skill-eligible; document the choice inline):
  ```python
  @pytest.mark.slow
  def test_day_force_makes_cell_appear():
      d = date(2026, 6, 16)
      la = {d: {"force": {("T013", "CT")}, "forbid": set()}}
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      assert "T013" in r.day_assignments.get(16, {}).get("CT", [])
      assert r.lock_conflicts == []

  @pytest.mark.slow
  def test_day_forbid_excludes_cell():
      # choose a (sid, loc, day) that IS in the golden, forbid it, assert it's gone
      d = date(2026, 6, 16)
      la = {d: {"force": set(), "forbid": {("T0XX", "病CT")}}}  # fill from golden
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      assert "T0XX" not in r.day_assignments.get(16, {}).get("病CT", [])

  @pytest.mark.slow
  def test_day_off_lock_keeps_staff_off():
      d = date(2026, 6, 16)
      la = {d: {"force": {("T0YY", "休")}, "forbid": set()}}  # a staff normally working day 16
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      worked = any("T0YY" in ids for loc, ids in r.day_assignments.get(16, {}).items()
                   if loc not in ("休", "○"))
      assert not worked
  ```
  (Before writing concrete IDs, read `tests/golden/2026-06_assignments.json` to pin a real eligible/assigned staff for each case; record the reasoning in a comment.)

- [ ] **Step 2 (GREEN).** In `day_scheduler.py`, immediately **before** `model.Maximize(...)` (`:1229`), after all `x` vars (`:719,:786`) and constraints, inject:
  ```python
  # --- Partial-lock re-solve injection (assumptions: enforce + diagnosable) ---
  locks = (self.locked_assignments or {}).get(current_date, {})
  lit_map = {}  # literal-index -> (sid, loc, iso_date, mode)
  for sid, lc in locks.get('force', ()):
      if lc == '夜':
          continue  # night-domain entry; not handled by day model
      if lc in ('休', '○'):
          vars_s = [x[sid, l.code] for l in target_locations if (sid, l.code) in x]
          if vars_s:
              aux = model.NewBoolVar(f'offlock_{sid}_{current_date.isoformat()}')
              model.Add(sum(vars_s) == 0).OnlyEnforceIf(aux)
              model.AddAssumption(aux)
              lit_map[aux.Index()] = (sid, lc, current_date.isoformat(), 'force_off')
          # else: staff already has no work var that day -> already off (no-op)
      elif (sid, lc) in x:
          lit = x[sid, lc]
          model.AddAssumption(lit)
          lit_map[lit.Index()] = (sid, lc, current_date.isoformat(), 'force')
      else:
          self.unlockable_locks.append(
              {'staff_id': sid, 'location': lc,
               'date': current_date.isoformat(), 'reason': 'no_var'})
  for sid, lc in locks.get('forbid', ()):
      if lc == '夜':
          continue
      if (sid, lc) in x:
          neg = x[sid, lc].Not()
          model.AddAssumption(neg)
          lit_map[neg.Index()] = (sid, lc, current_date.isoformat(), 'forbid')
  ```
  Use the actual name of the per-loc list in scope (`target_locations`; confirm by reading `_schedule_one_day` around `:666` and the `vars_s` construction at `:997`). Keep `lit_map` in local scope for now; Task 5 wires it to `lock_conflicts`. **Guard:** when `locks` is `{}` the loops are empty → zero `AddAssumption` calls → gate preserved.

- [ ] **Step 3 (GREEN).** Run the new slow tests **and** re-run the Task 1 gate. All green. If a forbid/off test is INFEASIBLE, the cause is a hard-constraint collision — pick a different cell (Task 5 handles genuine conflicts).

- [ ] **Commit:** `feat(p2b): day-scheduler lock injection (force/forbid/off) via CP-SAT assumptions`

---

## Task 4 — Pruned-var forces are reported, not swallowed

**Goal:** A force on a staff who has no BoolVar that day (night-before, holiday request, 業配/業出, T002-PET, T022-DX, 6-consec → `forced_holidays`, no `x`) must surface in `ScheduleResult.unlockable_locks`, never silently vanish.

- [ ] **Step 1 (RED).** Slow test:
  ```python
  @pytest.mark.slow
  def test_force_on_pruned_staff_is_reported():
      # pick (sid, day) where sid is in forced_holidays that day (e.g. a holiday-request staff)
      d = date(2026, 6, 16)
      la = {d: {"force": {("T0ZZ", "CT")}, "forbid": set()}}  # T0ZZ has no var day 16
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      assert any(u["staff_id"] == "T0ZZ" and u["location"] == "CT"
                 and u["date"] == "2026-06-16" for u in r.unlockable_locks)
      # the solve still completes (advisory, not fatal)
      assert r.day_assignments  # non-empty
  ```
  (Read the golden / a staff with a `★`/`☆` request on day 16 to pick a guaranteed-pruned staff; document.)

- [ ] **Step 2 (GREEN).** The `else: self.unlockable_locks.append(...)` branch from Task 3 already records it. Ensure `run_schedule` copies `day_scheduler.unlockable_locks` into the `ScheduleResult` (done in Task 1 Step 3). Confirm `unlockable_locks` accumulates across all days (it lives on the instance, appended per `_schedule_one_day`).

- [ ] **Step 3 (GREEN).** Re-run Task 1 gate (an empty lock set yields `unlockable_locks == []`). Green.

- [ ] **Commit:** `feat(p2b): report pruned-var forces as unlockable_locks (no silent no-op)`

---

## Task 5 — Night-scheduler lock injection (`'夜'`-domain only)

**Goal:** Implement and unit-prove the night occupancy force/forbid path, and prove day-domain locks do **not** leak into the night model.

- [ ] **Step 1 (RED).** Slow tests:
  ```python
  @pytest.mark.slow
  def test_night_force_occupancy():
      d = date(2026, 6, 12)
      la = {d: {"force": {("T0NN", "夜")}, "forbid": set()}}  # a night-capable staff
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      assert "T0NN" in r.night_assignments.get(12, [])

  @pytest.mark.slow
  def test_day_domain_lock_does_not_force_a_night():
      d = date(2026, 6, 12)
      la = {d: {"force": {("T013", "CT")}, "forbid": set()}}  # day-domain only
      base_nights = run_schedule(2026, 6, data_dir=DATA_DIR).night_assignments
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      # day-domain force must not have added T013 to nights via the night model
      assert ("T013" in r.night_assignments.get(12, [])) == ("T013" in base_nights.get(12, []))
  ```
  (Pick `T0NN` as a `can_night_shift` staff from the staff master.)

- [ ] **Step 2 (GREEN).** In `night_scheduler.py.schedule`, between `_add_soft_constraints(...)` (`:63`) and `solver = cp_model.CpSolver()` (`:67`), inject:
  ```python
  # --- Partial-lock re-solve injection (night = occupancy; '夜'-domain only) ---
  _locks = locked_assignments or {}
  for d in self.dates:
      dl = _locks.get(d, {})
      for sid, lc in dl.get('force', ()):
          if lc == NIGHT_LOC and (sid, d) in x:
              model.AddAssumption(x[sid, d])
      for sid, lc in dl.get('forbid', ()):
          if lc == NIGHT_LOC and (sid, d) in x:
              model.AddAssumption(x[sid, d].Not())
  ```
  Import `NIGHT_LOC` from `shift_scheduler.src.lock_utils`. **Note:** the day-domain `('T013','CT')` entry has `lc != '夜'` → skipped → no night effect. Empty lock set → zero assumptions → gate preserved. (Night INFEASIBLE diagnostics: extend Task 6's pattern if night locks ever ship; for v1 the `/resolve` builder emits no night locks, so this stays simple.)

- [ ] **Step 3 (GREEN).** Run the night tests + Task 1 gate. Green.

- [ ] **Commit:** `feat(p2b): night-scheduler '夜'-domain lock injection (occupancy only)`

---

## Task 6 — Post-processor lock-awareness (BIGGEST RISK)

**Goal:** Prove locked day cells survive `rebalance_workload`, `optimize_assignments_cpsat`, and `assign_monthly_off_days`. The shared `reassert_locks` safety net is the load-bearing guarantee; in-model pinning in the CP-SAT optimizer is an optimization.

- [ ] **Step 1 (RED).** Slow tests that force a cell and assert it survives the *full* `run_schedule` (which runs all three post-processors), plus targeted unit tests calling each post-processor directly with a synthetic `day_result_list` + a lock and asserting the locked cell is intact afterward:
  ```python
  @pytest.mark.slow
  def test_locked_cell_survives_all_post_processors():
      d = date(2026, 6, 16)
      la = {d: {"force": {("T013", "CT")}, "forbid": set()}}
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      assert "T013" in r.day_assignments.get(16, {}).get("CT", [])

  def test_rebalance_preserves_locked_cell():
      # build a minimal day_result_list with T013->CT on day 16 + a swap candidate,
      # call rebalance_workload(..., locked_assignments=la); assert T013 still CT/16
      ...

  def test_optimize_cpsat_preserves_locked_cell():
      ...  # call optimize_assignments_cpsat(..., locked_assignments=la), assert intact

  def test_assign_off_days_does_not_overwrite_locked_work_cell():
      ...  # locked work cell on a public-off day must NOT become 休
  ```
  (The three unit tests can be fast if the synthetic inputs are tiny; `optimize_assignments_cpsat` runs a small CP-SAT model — if it is slow with the minimal input, mark it `@pytest.mark.slow`. Prefer fast where feasible.)

- [ ] **Step 2 (GREEN).** Add `locked_assignments=None` to all three signatures:
  - `rebalance_workload` (`main.py:512`): when non-empty, build `pinned = {(sid, d.day) ...}` from the force set; **skip** any candidate swap whose source or target touches a pinned `(sid, day)`; after the function's main loop, call `reassert_locks(...)` on the result. When `None`/empty, the function is byte-identical to today (early return path: no pinning, no reassert).
  - `optimize_assignments_cpsat` (`main.py:754`): when non-empty, inside its CP-SAT model pin each locked work cell `model.Add(x[sid, loc] == 1)` and each OFF-lock `sum(work vars)==0` (read its var construction; mirror the day-scheduler pattern, but here plain `Add` is fine — this model has its own accept/reject gate and we are not diagnosing it). After it returns (whether it accepted or rejected), call `reassert_locks(...)`. When `None`/empty, unchanged.
  - `assign_monthly_off_days` (`main.py:19`): when non-empty, after it finishes the blank→休 materialization (`:147-155`), call `reassert_locks(...)`. (It only adds 休 to blanks, so a locked work cell is normally untouched; the reassert is a defensive guarantee and is the asserted contract.) When `None`/empty, unchanged.
  - Thread `locked_assignments=locked_assignments` at the three call sites (`main.py:1175,:1180,:1185`).

- [ ] **Step 3 (GREEN).** Run all Task 6 tests + the Task 1 gate. The gate proves the empty path is untouched; the lock tests prove survival. Green.

- [ ] **Commit:** `feat(p2b): lock-aware post-processors (reassert_locks after rebalance/optimize/off-days)`

---

## Task 7 — Infeasibility diagnostics (assumption conflict → exact offending cells)

**Goal:** A lock that collides with a genuinely hard constraint returns the exact conflicting cells via `solver.SufficientAssumptionsForInfeasibility()` rather than silently degrading the day to `forced_holidays`-only.

- [ ] **Step 1 (RED).** Slow test that forces a guaranteed-infeasible lock (two work locations for one staff on one day → violates one-loc-per-staff `sum(vars_s)<=1` at `day_scheduler.py:999`):
  ```python
  @pytest.mark.slow
  def test_conflicting_lock_reports_offending_cells():
      d = date(2026, 6, 16)
      la = {d: {"force": {("T013", "CT"), ("T013", "病CT")}, "forbid": set()}}
      r = run_schedule(2026, 6, data_dir=DATA_DIR, locked_assignments=la)
      cells = {(c["staff_id"], c["location"], c["date"]) for c in r.lock_conflicts}
      assert ("T013", "CT", "2026-06-16") in cells
      assert ("T013", "病CT", "2026-06-16") in cells
  ```
  (Confirm `T013` has BoolVars for both `CT` and `病CT` on day 16 by reading the golden / skills; otherwise the conflict is a pruned-var case, not an assumption conflict. Choose a staff/day where both vars exist.)

- [ ] **Step 2 (GREEN).** In `day_scheduler.py`, after `status = solver.Solve(model)` (`:1240`), before the `if status in [OPTIMAL, FEASIBLE]:` branch, add:
  ```python
  if status == cp_model.INFEASIBLE and lit_map:
      for idx in solver.SufficientAssumptionsForInfeasibility():
          info = lit_map.get(idx)
          if info:
              sid, loc, iso, mode = info
              self.lock_conflicts.append(
                  {'staff_id': sid, 'location': loc, 'date': iso, 'mode': mode})
  ```
  Keep the existing degraded-return (`return forced_holidays, location_needs`, `:1254`) so the run completes; `lock_conflicts` carries the actionable diagnosis up to `ScheduleResult` (already wired in Task 1). **Implementation note to verify:** for a negated literal `x[k].Not()`, store and look up by that literal object's `.Index()` (CP-SAT negated-literal indices are negative); confirm `SufficientAssumptionsForInfeasibility()` returns indices in the same space, and add an assertion in the test if the mapping needs the `lit.Index()` of the exact object you passed to `AddAssumption`.

- [ ] **Step 3 (GREEN).** Run the conflict test + Task 1 gate (empty set → `lock_conflicts == []`). Green.

- [ ] **Commit:** `feat(p2b): assumption-based lock_conflicts via SufficientAssumptionsForInfeasibility`

---

## Task 8 — `POST /rosters/{rid}/resolve` endpoint + `resolve_roster` (fast wiring, mocked solve)

**Goal:** Wire the endpoint and the re-freeze/synthetic-edit logic, tested **fast** by monkeypatching `RUNNER` with a canned `ScheduleResult` (no real solver).

- [ ] **Step 1 (RED).** Add fast tests to `tests/test_lock_resolve.py` (reuse the P2a-2 test-DB override + synthetic `freeze_roster` pattern — see `tests/test_roster_api.py`):
  ```python
  def test_resolve_keeps_locked_replaces_unlocked(client, conn, seeded_roster):
      rid = seeded_roster
      # lock T013->CT on 2026-06-16
      client.post(f"/rosters/{rid}/edits", json={
          "expected_version": 0, "op": "toggle_lock",
          "staff_id": "T013", "date": "2026-06-16", "location": "CT", "locked": True})
      # monkeypatch RUNNER to a fake that asserts it got the lock and returns a canned result
      ...
      resp = client.post(f"/rosters/{rid}/resolve", json={})
      assert resp.status_code == 200
      body = resp.json()
      assert body["version"] > 0
      # locked cell preserved, an unlocked cell changed to the fake's output
      assert "T013" in body["grid"]["rows_by_id"]["T013"]...  # adapt to grid shape
      # a synthetic op='resolve' edit was recorded and is undoable
      edits = conn.execute("SELECT op FROM roster_edits WHERE roster_id=? ORDER BY seq", (rid,)).fetchall()
      assert edits[-1]["op"] == "resolve"

  def test_resolve_returns_422_on_lock_conflict(client, seeded_roster):
      # fake RUNNER returns a ScheduleResult with lock_conflicts set
      resp = client.post(f"/rosters/{seeded_roster}/resolve", json={})
      assert resp.status_code == 422
      assert "conflicts" in resp.json()["detail"]

  def test_resolve_surfaces_unlockable(client, seeded_roster):
      # fake RUNNER returns unlockable_locks; assert they appear in the 200 body
      ...

  def test_resolve_is_undoable(client, conn, seeded_roster):
      # after resolve, POST /undo restores the pre-resolve grid
      ...
  ```
  The fake runner asserts `locked_assignments` was threaded:
  ```python
  def fake_runner(year, month, data_dir, *, locked_assignments=None, **kw):
      assert locked_assignments and date(2026,6,16) in locked_assignments
      assert ("T013","CT") in locked_assignments[date(2026,6,16)]["force"]
      return ScheduleResult(year=year, month=month, staff=[...],
                            day_assignments={16:{"CT":["T013"], "MG":["T099"]}, ...},
                            night_assignments={...}, requests={...},
                            on_call_assignments={...}, daikyu_counts={...}, off_counts={...},
                            validation_errors=[])
  ```

- [ ] **Step 2 (GREEN).** In `webapp/api/rosters.py` add:
  - `class LockConflictError(Exception): def __init__(self, conflicts): self.conflicts = conflicts`.
  - `resolve_roster(conn, rid, *, runner, user_id=None) -> dict`:
    1. Load header (`year, month, data_dir, target_holidays, version, edit_cursor`); 404 via `KeyError` if missing.
    2. `locked_rows = [dict(r) for r in conn.execute("SELECT staff_id,date,kind,location_or_role,locked FROM roster_assignments WHERE roster_id=? AND kind='day' AND locked=1", (rid,))]`; `la = day_locks_from_rows(locked_rows)`.
    3. Pre-validate: `errs = validate_lock_set(la, daily_location_needs=roster_to_dicts(conn,rid)["daily_location_needs"])`; if `errs` → `raise LockConflictError({"stage":"pre_validate","errors":errs})`.
    4. `before = _all_day_rows_snapshot(conn, rid)` (full `roster_assignments` rows, all kinds).
    5. Re-solve serialized: `from webapp.api.jobs import _solve_lock` then `with _solve_lock: result = runner(year, month, data_dir, locked_assignments=la)`.
    6. If `getattr(result, "lock_conflicts", [])` → `raise LockConflictError({"stage":"solve","conflicts":result.lock_conflicts})`.
    7. Re-freeze: delete all **unlocked** rows (`DELETE ... WHERE roster_id=? AND NOT (kind='day' AND locked=1)`); insert from `result` via `_resolve_rows_from_result(result)` **skipping** any `(sid, iso, 'day')` already present as a locked row (keep the locked version). Reuse the `freeze_roster` row-mapping shape.
    8. `after = _all_day_rows_snapshot(conn, rid)`.
    9. Append `roster_edits`: `seq = edit_cursor + 1`; delete redo tail (`seq > edit_cursor`); insert `op='resolve'`, `payload_json = {"locked": [...]} `, `before_json = before`, `after_json = after`; `version += 1`, `edit_cursor = seq`.
    10. `affected_staff = {r["staff_id"] for r in before + after}`; `warnings, _, _ = _recompute_and_persist(conn, rid, affected_staff)`; `grid, d = build_roster_grid(conn, rid)`; `conn.commit()`.
    11. Return `{"version": new_version, "grid": grid, "warnings": _warnings_payload(warnings), "unlockable": getattr(result, "unlockable_locks", [])}`.
  - `_all_day_rows_snapshot(conn, rid)` → list of full rows (same columns `_restore_rows` consumes); `_resolve_rows_from_result(result)` → mirrors `freeze_roster`'s `rows` build (day/night/oncall/request, `locked=0`).
  - **Undo compatibility:** because `before/after_json` are full row snapshots, the existing `_undo_redo` path restores them via `_restore_rows` over `cells = union of (sid, day)`; confirm `_undo_redo` derives `cells` from both snapshots (it does, `rosters.py:400-401`).

- [ ] **Step 3 (GREEN).** In `webapp/api/main.py`, add the endpoint after `/redo`:
  ```python
  @app.post("/rosters/{rid}/resolve")
  def post_resolve(rid: int, payload: Dict[str, Any] = None, conn=Depends(get_db)):
      _roster_or_404(conn, rid)
      try:
          return roster_ops.resolve_roster(conn, rid, runner=RUNNER)
      except roster_ops.LockConflictError as exc:
          raise HTTPException(status_code=422, detail=exc.conflicts)
  ```
  `RUNNER` is the existing module-level indirection (`main.py:15`) so tests monkeypatch `webapp.api.main.RUNNER`.

- [ ] **Step 4 (GREEN).** Run `python -m pytest tests/test_lock_resolve.py -m "not slow"` — all fast `/resolve` tests green. Re-run the full fast suite to confirm no regression: `python -m pytest -m "not slow"`.

- [ ] **Commit:** `feat(p2b): POST /rosters/{rid}/resolve — re-solve under lock, re-freeze, synthetic resolve edit`

---

## Task 9 — End-to-end slow proof (real solver through `/resolve`)

**Goal:** One real-solver integration test proving the whole path and re-confirming determinism.

- [ ] **Step 1 (RED→GREEN).** Slow test: freeze a *real* 2026-06 roster (reuse the slow fixture path), lock one real work cell, call `/resolve` with `RUNNER = run_schedule` (the real solver), assert: status 200, the locked cell is present in the returned grid, version bumped, an `op='resolve'` edit exists. Then call `/resolve` a second time on the same locks and assert the returned grid is identical (determinism across two real re-solves).
  ```python
  @pytest.mark.slow
  def test_resolve_real_solver_preserves_lock_and_is_deterministic(real_client, real_roster):
      ...
  ```

- [ ] **Step 2.** Run `python -m pytest tests/test_lock_resolve.py -m slow` (full file) + `tests/test_parity_golden.py -m slow`. All green.

- [ ] **Commit:** `test(p2b): end-to-end /resolve real-solver lock-preservation + determinism`

---

## Self-Review

**Spec coverage (synthesis §4 / spec §7):**
- Lock-set shape `{date: {force/forbid: set[(sid,loc)]}}` — Architecture + Task 2/3. ✅
- Thread through `run_schedule` → `DayScheduler(__init__)` + inject before `Maximize` (`:1229`) — Task 1/3. ✅
- Thread through `NightScheduler.schedule` + inject after `_add_soft_constraints` (`:63`) before `CpSolver` (`:67`) — Task 1/5. ✅
- Pruned-var force reported (not swallowed) — Task 4 (`unlockable_locks`). ✅
- Night dense vars / role non-forcible (occupancy only, `'夜'`-domain) — Task 5. ✅
- Post-processor lock-awareness for all three helpers + explicit survival tests — Task 6 (BIGGEST RISK). ✅
- Infeasibility: pre-validation (Task 2) **and** `AddAssumption` + `SufficientAssumptionsForInfeasibility` (Task 7) — both. ✅
- `/resolve`: read locked rows → build lock set → `_solve_lock` (seed=42, num_workers=1) → re-freeze (keep locked / replace unlocked) → synthetic `op='resolve'` undoable edit → return grid+warnings+version — Task 8. ✅
- Determinism unchanged: no edits to seed/workers/deterministic-time; empty-lock byte-identity gate established first and re-run every task — Determinism contract + Task 1. ✅

**Placeholder scan:** Concrete `(staff_id, loc, day)` values in Tasks 3/4/5/7 are written as `T0XX/T0YY/T0ZZ/T0NN` placeholders **by design** — each step instructs the implementer to read `tests/golden/2026-06_assignments.json` + skills to pin real eligible IDs and document the choice. No placeholder remains in shipped code; they live only in test setup that must be resolved before the test is valid.

**Type consistency:** Lock-set keys are `datetime.date` in-solver; persistence/JSON is ISO `YYYY-MM-DD`; `day_locks_from_rows` converts at the boundary. `unlockable_locks`/`lock_conflicts` are `list[dict[str,str]]`, excluded from `as_dict()`. `ScheduleResult` field additions use `field(default_factory=list)`. `recompute_stats` keeps its shipped dict-form signature (no `DayAssignment` objects in the edit/resolve loop). `reassert_locks` returns `list[DayAssignment]`.

**Determinism:** Enforcement is assumptions-only (zero calls when empty ⇒ byte-identical model, presolve, search, solution). Post-processors short-circuit to today's code path when the lock set is empty/None. `/resolve` serializes via `jobs._solve_lock`. Task 9 asserts two real re-solves are identical. The Task 1 gate is the contract and is re-run after every task.

**Risk encoded as a test (the single most important):** **Post-processor lock-awareness (Task 6).** The synthesis flags it as the biggest integration risk: the day re-solve re-runs `rebalance_workload`/`optimize_assignments_cpsat`/`assign_monthly_off_days`, any of which will silently move a CP-SAT-locked cell, undoing the lock after a successful solve. `test_locked_cell_survives_all_post_processors` (full `run_schedule`) plus per-helper unit tests pin the `reassert_locks` guarantee. **The empty-lock byte-identity gate** (Task 1, `test_empty_lock_set_is_byte_identical_to_today_and_golden`) is structured as: run `run_schedule(2026,6)` three ways — no kwarg, `locked_assignments=None`, `locked_assignments={}` — canonicalize each via `json.dumps(..., sort_keys=True)`, assert all three `as_dict()`s are equal **and** equal the committed `tests/golden/2026-06_assignments.json`; a companion test asserts the new lock fields never leak into `as_dict()`. It is established before any injection code exists and re-run at the end of every subsequent task, so determinism cannot silently regress.

## Next

After P2b is green, P2d wires the React **Re-solve** button (`EditToolbar`) to `POST /rosters/{rid}/resolve`, renders the `unlockable`/`conflicts` (422) responses in `WarningPanel`/`ConflictDialog`, and refetches the full grid on the bumped `version`. The night-lock extension (`'夜'`-domain locks from a night-cell lock toggle) and in-model night infeasibility diagnostics are the natural follow-ups if night cells become UI-lockable.
