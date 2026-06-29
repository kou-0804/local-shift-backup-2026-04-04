# Web App P2a-1 — Keystone Extractions (build_grid + recompute_stats) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the cell-text derivation and the off/代休 statistics logic out of `ExcelGenerator` / `main.py` into two pure, solver-free, openpyxl-free modules — `grid_derivation.py` and `stats_engine.py` — proven byte-identical to today's behaviour by golden tests. These two functions are the keystone every later P2 sub-phase (edit API, Direction-A Excel, React grid) reuses, so getting them exactly right and well-tested first de-risks all of P2.

**Architecture:** `grid_derivation.derive_cell_text()` is a verbatim lift of `ExcelGenerator._get_assignment_text` (no `self`); `grid_derivation.cell_fill()` lifts `_get_cell_fill`. `ExcelGenerator` then *delegates* to them (single source). `stats_engine` centralises the three holiday/work symbol sets (currently duplicated with drift across 4 functions) and provides `recompute_off_daikyu()` — a pure re-derivation of `off_counts`/`daikyu_counts` from the assignment dicts, matching `assign_monthly_off_days`. A `daily_location_needs` field is added to `ScheduleResult` so coverage can be recomputed later.

**Tech Stack:** Python 3.13, pytest. No new runtime deps.

**Scope note:** P2a-1 is a pure refactor + fixtures. NO SQLite, NO web endpoints, NO React, NO Excel redesign yet (those are P2a-2 / P2c / P2d). Determinism and existing behaviour must be unchanged — the golden tests prove it.

**Provenance (from the P2 internals map):**
- `ExcelGenerator._get_assignment_text` = `shift_scheduler/src/excel_generator.py:234-290`; `_get_cell_fill` = `:292-303`; stats counting loop = `:158-206`; `stats_columns` (21 labels) declared at `:100,144,316`; `クL`→`ク` remap at `:189`; off/daikyu injected from counts at `:195-196`.
- `assign_monthly_off_days` = `main.py:19-185`; status classification = `:97-132`; off/daikyu formulas = `:157-166`; single-day kernel `off_contrib` = `:862-886`. Symbol sets duplicated across `assign_monthly_off_days`, `pre_seed_rest_days`, `rebalance_workload`, `optimize_assignments_cpsat`.

---

## File Structure

- Create `tests/golden/gen_p2a1_fixture.py` — one-time generator (runs the real solver) that dumps a fixture of derivation inputs + expected cell texts + expected off/daikyu, captured from the CURRENT (pre-refactor) code.
- Create `tests/golden/2026-06_p2a1.json` — the generated fixture (committed).
- Create `shift_scheduler/src/grid_derivation.py` — `derive_cell_text()`, `cell_fill()`.
- Create `shift_scheduler/src/stats_engine.py` — symbol sets + `recompute_off_daikyu()`.
- Modify `shift_scheduler/src/excel_generator.py` — delegate `_get_assignment_text`/`_get_cell_fill` to `grid_derivation`.
- Modify `shift_scheduler/src/models/schedule_result.py` — add `daily_location_needs` field (NOT in `as_dict()`).
- Modify `main.py` — pass `daily_location_needs` into the returned `ScheduleResult`.
- Create `tests/test_grid_derivation.py`, `tests/test_stats_engine.py`.

All commands assume repo root `"/Users/kohei/Desktop/local-shift ver1"` is cwd and the venv is active (`source .venv/bin/activate`). Run tests with `python -m pytest`. The `slow` marker (real solver) is registered in `pytest.ini`.

---

## Task 1: Generate the P2a-1 golden fixture from current behaviour

This captures the EXACT current outputs BEFORE any refactor, so the extractions can be proven byte-identical. It runs the real solver once.

**Files:**
- Create: `tests/golden/gen_p2a1_fixture.py`
- Create (generated): `tests/golden/2026-06_p2a1.json`

- [ ] **Step 1: Write the generator script**

```python
# tests/golden/gen_p2a1_fixture.py
"""One-time fixture generator. Runs the real solver for 2026-06 and captures,
from the CURRENT (pre-refactor) code, the derivation inputs + expected cell texts
+ expected off/daikyu counts. Re-run only if the scheduler intentionally changes.
Usage: python tests/golden/gen_p2a1_fixture.py
"""
import json
from main import run_schedule
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.excel_generator import ExcelGenerator

YEAR, MONTH, DATA_DIR = 2026, 6, "shift_scheduler/data"


def main():
    result = run_schedule(YEAR, MONTH, data_dir=DATA_DIR)
    # Full Staff objects (needed for nuc_tx_ids via .note) — load directly.
    technicians = DataLoader(data_dir=DATA_DIR).load_all(f"{YEAR}-{MONTH:02d}")[0]
    active = [t for t in technicians if t.status == "在籍"]

    gen = ExcelGenerator(
        year=YEAR, month=MONTH, technicians=technicians,
        night_assignments=result.night_assignments,
        day_assignments=result.day_assignments,
        requests=result.requests,
        on_call_assignments=result.on_call_assignments,
        daikyu_counts=result.daikyu_counts, off_counts=result.off_counts,
        validation_errors=result.validation_errors,
    )
    days = gen.days_in_month
    expected_cells = {
        t.id: {str(d): gen._get_assignment_text(t.id, d) for d in range(1, days + 1)}
        for t in active
    }
    fixture = {
        "year": YEAR, "month": MONTH, "days_in_month": days,
        "nuc_tx_ids": sorted(gen.nuc_tx_ids),
        "active_staff_ids": [t.id for t in active],
        # derivation inputs (str day keys for JSON)
        "day_assignments": {str(d): v for d, v in result.day_assignments.items()},
        "night_assignments": {str(d): v for d, v in result.night_assignments.items()},
        "requests": {str(d): v for d, v in result.requests.items()},
        # expected outputs
        "expected_cells": expected_cells,
        "expected_off_counts": result.off_counts,
        "expected_daikyu_counts": result.daikyu_counts,
        "target_holidays": 9,
    }
    with open("tests/golden/2026-06_p2a1.json", "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, sort_keys=True, indent=2)
    print(f"wrote tests/golden/2026-06_p2a1.json: {len(active)} staff x {days} days")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixture (runs the real solver, ~2 min)**

Run: `python tests/golden/gen_p2a1_fixture.py`
Expected: prints `wrote tests/golden/2026-06_p2a1.json: 67 staff x 30 days` (counts may vary slightly). Confirm the file exists and `expected_off_counts` is non-empty.

- [ ] **Step 3: Commit the fixture + generator**

```bash
git add tests/golden/gen_p2a1_fixture.py tests/golden/2026-06_p2a1.json
git commit -m "test(p2a1): capture pre-refactor cell-text + off/daikyu golden fixture"
```

---

## Task 2: Extract `derive_cell_text` + `cell_fill` into `grid_derivation.py`

**Files:**
- Read: `shift_scheduler/src/excel_generator.py:234-303` (the two methods to lift)
- Create: `shift_scheduler/src/grid_derivation.py`
- Test: `tests/test_grid_derivation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grid_derivation.py
import json
from shift_scheduler.src.grid_derivation import derive_cell_text, cell_fill

with open("tests/golden/2026-06_p2a1.json", encoding="utf-8") as f:
    FIX = json.load(f)

# rebuild int-keyed dicts from the fixture
DAY = {int(d): v for d, v in FIX["day_assignments"].items()}
NIGHT = {int(d): v for d, v in FIX["night_assignments"].items()}
REQ = {int(d): v for d, v in FIX["requests"].items()}
NUC = set(FIX["nuc_tx_ids"])
DAYS = FIX["days_in_month"]


def test_derive_cell_text_matches_golden_for_every_cell():
    mismatches = []
    for sid, by_day in FIX["expected_cells"].items():
        for d_str, expected in by_day.items():
            d = int(d_str)
            got = derive_cell_text(sid, d, DAY, NIGHT, REQ, NUC)
            if got != expected:
                mismatches.append((sid, d, expected, got))
    assert not mismatches, f"{len(mismatches)} cell mismatches, first 5: {mismatches[:5]}"


def test_cell_fill_known_values():
    assert cell_fill("病CT夜") == "FFFF00"   # night → yellow (substring '夜' tested first)
    assert cell_fill("○") == "FFC0CB"        # 明け → pink
    assert cell_fill("休") == "D3D3D3"        # off → grey
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_grid_derivation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shift_scheduler.src.grid_derivation'`.

- [ ] **Step 3: Create `grid_derivation.py` by lifting the two methods verbatim**

Open `shift_scheduler/src/excel_generator.py` and copy `_get_assignment_text` (`:234-290`) and `_get_cell_fill` (`:292-303`) into the new module as module-level functions, replacing every `self.day_assignments`→`day_assignments`, `self.night_assignments`→`night_assignments`, `self.requests`→`requests`, `self.nuc_tx_ids`→`nuc_tx_ids`. Keep the logic and ordering **exactly** (the precedence is order-sensitive). Skeleton:

```python
# shift_scheduler/src/grid_derivation.py
"""Pure cell-text + fill derivation, lifted verbatim from ExcelGenerator so the
Excel renderer, the web grid, and edit responses all share one source of truth.
No openpyxl, no solver. Keep the precedence EXACTLY as the original."""


def derive_cell_text(tech_id, day, day_assignments, night_assignments, requests, nuc_tx_ids):
    # --- verbatim body of ExcelGenerator._get_assignment_text, self.X -> X params ---
    # Step A: parts from day_assignments
    # Step B: night '夜' suffix on parts[0]
    # Step C: 明け '○' early return if prev-day night
    # Step D: read req_symbol
    # Step E: 夜希 -> '(希)'
    # Step F: 17業/17休 extra part
    # Step G: no parts -> req_symbol (except '休(仮)')
    # Step H: nuc/tx ['休'] blanking
    # Step I: ['休'] + real request override
    # Step J: '/'.join(parts)
    ...


def cell_fill(text):
    # --- verbatim body of ExcelGenerator._get_cell_fill, returns hex str or None ---
    ...
```

Copy the real bodies from the source — do not paraphrase. (The `...` above are placeholders for YOU to fill from the source file; the committed module must contain the real code, no `...`.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_grid_derivation.py -v`
Expected: PASS (every cell matches the golden; fills match).

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/grid_derivation.py tests/test_grid_derivation.py
git commit -m "feat(grid): extract pure derive_cell_text + cell_fill (byte-identical to ExcelGenerator)"
```

---

## Task 3: Make `ExcelGenerator` delegate to `grid_derivation` (single source)

**Files:**
- Modify: `shift_scheduler/src/excel_generator.py:234-303`
- Test: `tests/test_excel_bytes.py` (existing) + reuse `tests/test_parity_golden.py` (slow)

- [ ] **Step 1: Replace the two method bodies with delegations**

In `excel_generator.py`, replace the body of `_get_assignment_text` with:

```python
    def _get_assignment_text(self, tech_id, day):
        from shift_scheduler.src.grid_derivation import derive_cell_text
        return derive_cell_text(tech_id, day, self.day_assignments,
                                self.night_assignments, self.requests, self.nuc_tx_ids)
```

and the body of `_get_cell_fill` with:

```python
    def _get_cell_fill(self, text):   # keep the original parameter name from the source
        from shift_scheduler.src.grid_derivation import cell_fill
        return cell_fill(text)
```

(If `_get_cell_fill`'s parameter is named differently in the source, keep that name and pass it through.)

- [ ] **Step 2: Run the fast Excel test**

Run: `python -m pytest tests/test_excel_bytes.py -v`
Expected: PASS (generate_bytes still works).

- [ ] **Step 3: Run the slow end-to-end parity to confirm nothing changed**

Run: `python -m pytest tests/test_parity_golden.py -v -m slow`
Expected: PASS — the schedule data-parity golden is unaffected (this proves the delegation didn't change scheduler output; the cell golden in Task 2 already proved derivation identity).

- [ ] **Step 4: Commit**

```bash
git add shift_scheduler/src/excel_generator.py
git commit -m "refactor(excel): delegate cell derivation/fill to grid_derivation (single source)"
```

---

## Task 4: `stats_engine.py` — centralised symbol sets + `recompute_off_daikyu`

**Files:**
- Read: `main.py:19-185` (`assign_monthly_off_days`), `main.py:862-886` (`off_contrib`)
- Create: `shift_scheduler/src/stats_engine.py`
- Test: `tests/test_stats_engine.py`

`recompute_off_daikyu` re-derives `off_counts`/`daikyu_counts` purely from the assignment dicts (no solver, no mutation), reproducing `assign_monthly_off_days`'s status classification (`main.py:97-132`) and formulas (`:157-166`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stats_engine.py
import json
from shift_scheduler.src.stats_engine import recompute_off_daikyu

with open("tests/golden/2026-06_p2a1.json", encoding="utf-8") as f:
    FIX = json.load(f)

DAY = {int(d): v for d, v in FIX["day_assignments"].items()}
NIGHT = {int(d): v for d, v in FIX["night_assignments"].items()}
REQ = {int(d): v for d, v in FIX["requests"].items()}


def test_recompute_off_daikyu_matches_golden():
    off, daikyu = recompute_off_daikyu(
        day_assignments=DAY, night_assignments=NIGHT, requests=REQ,
        staff_ids=FIX["active_staff_ids"], year=FIX["year"], month=FIX["month"],
        target_holidays=FIX["target_holidays"],
    )
    # daikyu is only stored when > 0 downstream (.get(sid,0)); compare on that basis
    assert off == FIX["expected_off_counts"]
    assert {k: v for k, v in daikyu.items() if v} == \
           {k: v for k, v in FIX["expected_daikyu_counts"].items() if v}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_stats_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shift_scheduler.src.stats_engine'`.

- [ ] **Step 3: Implement `stats_engine.py`**

Port `assign_monthly_off_days`'s per-day status classification and formulas into a pure function. Define the symbol sets ONCE here (copy the exact membership from `main.py`'s `assign_monthly_off_days`). The function takes the dict form of assignments (not `DayAssignment` lists) and must NOT mutate anything.

```python
# shift_scheduler/src/stats_engine.py
"""Single source for the holiday/work symbol vocabularies and a pure,
solver-free recomputation of off (公休) / daikyu (代休) counts from the
assignment dicts. Mirrors main.py assign_monthly_off_days exactly so stats
can be refreshed after a manual edit without re-running the solver."""
import calendar
from datetime import date
import jpholiday

# Copy these EXACTLY from main.py assign_monthly_off_days (single source now).
PURE_HOLIDAY_SYMS = {...}          # e.g. {'★','★連','☆','☆小','☆デ','◆','出/☆','退職','☆育', ...}
CONDITIONAL_HOLIDAY_SYMS = {...}
FORCED_WORK_SYMS = {...}


def _is_public_off(d: date) -> bool:
    is_jan_holiday = (d.month == 1 and d.day in (1, 2, 3))
    return d.weekday() == 6 or jpholiday.is_holiday(d) or is_jan_holiday


def recompute_off_daikyu(day_assignments, night_assignments, requests,
                         staff_ids, year, month, target_holidays):
    """Return (off_counts: dict[sid,float], daikyu_counts: dict[sid,float]).
    off = #off + #blank + 0.5*#half ; daikyu = max(0, target - off)."""
    num_days = calendar.monthrange(year, month)[1]
    off_counts, daikyu_counts = {}, {}
    for sid in staff_ids:
        off = 0.0
        for dnum in range(1, num_days + 1):
            d = date(year, month, dnum)
            # classify status: work | off | half | blank  (first match wins,
            # mirroring main.py:97-132 — see the source for exact branch order)
            status = _classify(sid, d, dnum, day_assignments, night_assignments, requests)
            if status == 'off':
                off += 1.0
            elif status == 'half':
                off += 0.5
            elif status == 'blank':
                off += 1.0   # unassigned weekday = effective rest (off_contrib=1.0)
            # 'work' contributes 0
        off_counts[sid] = off
        dk = max(0.0, target_holidays - off)
        daikyu_counts[sid] = dk
    return off_counts, daikyu_counts
```

Implement `_classify(sid, d, dnum, day_assignments, night_assignments, requests)` to reproduce `main.py:97-132` exactly: night/明け→work; `FORCED_WORK_SYMS`→work; `'出/☆'`→half; `PURE_HOLIDAY_SYMS`/`'休'`/loc=='休'→off; `CONDITIONAL_HOLIDAY_SYMS`→off-if-public-else-work; public-off & no real loc→off; real loc (not 休/○)→work; `'17休'`→off; other request (≠`'休(仮)'`)→work; else→blank. Read the source to get the branch order and the membership of the symbol sets exactly right — the test in Step 1 is the byte-identity gate.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_stats_engine.py -v`
Expected: PASS. If it fails, diff which staff's off/daikyu differ and fix `_classify`/symbol membership to match `main.py` — do not adjust the test.

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/stats_engine.py tests/test_stats_engine.py
git commit -m "feat(stats): pure recompute_off_daikyu + centralized symbol sets (matches assign_monthly_off_days)"
```

---

## Task 5: Add `daily_location_needs` to `ScheduleResult` (coverage recompute input)

**Files:**
- Modify: `shift_scheduler/src/models/schedule_result.py`
- Modify: `main.py` (run_schedule return)
- Test: `tests/test_schedule_result.py` (extend)

`daily_location_needs` is a solver output (`main.py:1174`) needed later to recompute coverage warnings. Add it as a field but keep it OUT of `as_dict()` so the existing data-parity golden is unaffected.

- [ ] **Step 1: Write the failing test (extend `tests/test_schedule_result.py`)**

```python
# append to tests/test_schedule_result.py
def test_daily_location_needs_field_default_and_excluded_from_as_dict():
    r = ScheduleResult(
        year=2026, month=6, staff=[], day_assignments={}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={},
        validation_errors=[],
    )
    assert r.daily_location_needs == {}              # default
    assert "daily_location_needs" not in r.as_dict()  # excluded from parity dict
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_schedule_result.py -v`
Expected: FAIL (`TypeError`/`AttributeError` — field doesn't exist).

- [ ] **Step 3: Add the field**

In `shift_scheduler/src/models/schedule_result.py`, add after `workbook_bytes`:

```python
    daily_location_needs: dict = field(default_factory=dict)  # {date or day: {loc_code: required}}
```

Add `from dataclasses import dataclass, field` if `field` isn't already imported. Do NOT add it to `as_dict()`.

- [ ] **Step 4: Populate it in `run_schedule`**

In `main.py` `run_schedule`, the `daily_location_needs` local (returned by `day_scheduler.schedule(...)`) is in scope at the `ScheduleResult(...)` return. Add `daily_location_needs=daily_location_needs,` to the `ScheduleResult(...)` constructor call.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_schedule_result.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shift_scheduler/src/models/schedule_result.py main.py tests/test_schedule_result.py
git commit -m "feat(model): add daily_location_needs to ScheduleResult (coverage recompute input)"
```

---

## Task 6: Full-suite green gate

**Files:** none (verification only)

- [ ] **Step 1: Run the fast suite**

Run: `python -m pytest -m "not slow" -v`
Expected: ALL pass — `test_grid_derivation`, `test_stats_engine`, `test_schedule_result`, `test_excel_bytes`, `test_api`, and the pre-existing `test_rebalancer_helpers`.

- [ ] **Step 2: (recommended) run the slow gate**

Run: `python -m pytest -m slow -v`
Expected: PASS — proves the refactor left scheduler output and Excel derivation unchanged.

No commit (verification only).

---

## Self-Review

**Spec coverage (P2a-1 slice of the P2 design §1.1, §1.2):**
- `build_grid` derivation core (`derive_cell_text` + `cell_fill`) extracted, byte-identical → Tasks 1,2,3. ✅
- `recompute_stats` off/daikyu core + centralized symbol sets → Tasks 1,4. ✅
- `daily_location_needs` persisted for later coverage recompute → Task 5. ✅
- Full grid-dict assembly (`build_grid` returning rows/stats/oncall), coverage/HB/consecutive recompute, SQLite persistence, edit API, Direction-A Excel, React → **deferred to P2a-2 / P2c / P2d** (stated in scope note). The two pure cores they depend on are delivered and tested here.

**Placeholder scan:** Tasks 2 and 4 contain `...`/`{...}` ONLY as explicit "copy the real body from the cited source lines" markers, with the source location given; the committed code must contain the real bodies (the golden tests fail otherwise). All test code and commands are concrete.

**Type consistency:** `derive_cell_text(tech_id, day, day_assignments, night_assignments, requests, nuc_tx_ids)` and `recompute_off_daikyu(day_assignments, night_assignments, requests, staff_ids, year, month, target_holidays)` signatures are used identically in the tests and (Task 3) the ExcelGenerator delegation. Fixture keys (`expected_cells`, `expected_off_counts`, `expected_daikyu_counts`, `active_staff_ids`, `nuc_tx_ids`, `days_in_month`, `target_holidays`) match between the generator (Task 1) and the consumers (Tasks 2,4).

---

## Next (separate plans)
- **P2a-2:** full `build_grid` dict assembly (rows+stats+oncall) + coverage/HB/consecutive recompute; SQLite roster/assignment/edit tables; `/freeze`, `/rosters/{rid}`, `/edits` (assign/unassign/move/toggle_lock), `/undo`, `/redo`; optimistic concurrency.
- **P2c:** Direction-A Excel renderer consuming `build_grid`.
- **P2d:** React editor (TanStack Table + dnd-kit) against the P2a-2 API.
- **P2b:** partial-lock re-solve.
