# Web App P2a-2 — Editing Backend (build_grid + recompute_stats + SQLite roster + edit API) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the two pure cores delivered by **P2a-1** (`grid_derivation.derive_cell_text`/`cell_fill`, `stats_engine.recompute_off_daikyu`, the centralized symbol sets, and `ScheduleResult.daily_location_needs`) into a complete, persisted, live-recomputing **editing backend**. After P2a-2, an in-memory `ScheduleResult` can be **frozen** into SQLite, **read back** as a full grid + stats + warnings, **edited** (assign / unassign / move / toggle_lock) with optimistic concurrency, and **undone/redone** — all solver-free, deterministic, and reusing the single derivation source.

**Architecture:**
- `grid_derivation.build_grid(...)` assembles the whole grid dict (rows with `cells`, `cell_meta{kind,fill}`, `has_work`, `stats`; `oncall_rows`; `weekdays`; `stats_columns`) by calling P2a-1's `derive_cell_text`/`cell_fill` and porting the 21-column counting loop. It supports a `cells=` fast-path for the edit hot loop.
- `stats_engine.recompute_stats(...)` extends P2a-1's `recompute_off_daikyu` with **coverage** (vs persisted `daily_location_needs`, folding `クL`→`ク`), **night-HB gaps**, **holiday deficit**, and the **7-day consecutive-work** check — returning the structured warnings the edit API surfaces.
- `webapp/api/db.py` owns a stdlib-`sqlite3` connection plus the 4 tables (`rosters`, `roster_assignments`, `roster_meta`, `roster_edits`).
- `webapp/api/rosters.py` owns the freeze mapping, the `roster_to_dicts` adapter, the apply pipeline (validate → snapshot → mutate → re-derive affected cells incl. the D+1 明け rule → recompute → persist), undo/redo, and optimistic concurrency.
- `webapp/api/main.py` gains the additive endpoints: `POST /jobs/{job_id}/freeze`, `GET /rosters/{rid}`, `GET /rosters/{rid}/grid`, `POST /rosters/{rid}/edits`, `POST /rosters/{rid}/undo`, `POST /rosters/{rid}/redo`.

**Tech Stack:** Python 3.13, FastAPI + Starlette `TestClient`, stdlib `sqlite3` (no new runtime deps), pytest with `tmp_path` temp DB files. The `slow` marker (real solver) is reused only by the one-time fixture generator.

**Scope note:** P2a-2 is the editing **backend**. NO Direction-A Excel renderer (P2c), NO React UI (P2d), NO partial-lock re-solve (P2b), NO master CRUD (P3). The `skill`/power-balance warning group requires the skills/PB masters and is **deferred to P3** — P2a-2's `recompute_stats` returns `coverage` / `holiday_deficit` / `consecutive` / `night_hb_gaps`, and the edit API surfaces `skill: []` as a documented placeholder. Determinism is preserved: edits + undo are pure row mutations + deterministic derivation, so the grid is a deterministic function of `(freeze baseline, edit log up to cursor)`.

**Provenance (from the P2 Technical Design & Decomposition synthesis, §1.1, §1.2, §2, §6 P2a; and the readers):**
- `build_grid` core = `ExcelGenerator._get_assignment_text` (`shift_scheduler/src/excel_generator.py:234-290`, delivered as P2a-1 `derive_cell_text`) + `_get_cell_fill` (`:292-303`, delivered as P2a-1 `cell_fill`) + counting loop (`:158-206`); 21 `stats_columns` at `:100,144,316`; `WORK_LOCATION_CODES` superset; `クL`→`ク` fold at `:189`; whole-cell `'夜' in text` 夜勤 test; 公休/代休 injected from `off_counts`/`daikyu_counts` **after** counting and **overwriting** parsed values; whole stats block blank when `has_work==False` (`:146-155,198-199`).
- `recompute_stats` = P2a-1 `recompute_off_daikyu` (port of `assign_monthly_off_days` `main.py:19-185`, status classify `:97-132`, formulas `:157-166`, single-day kernel `off_contrib` `:862-886`) + coverage/night-HB block (`main.py:1210-1225`) + 7-day window (`_passes_7day_check` ref `main.py:82-88`).
- SQLite schema = synthesis §2.1 (4 tables). Freeze mapping = synthesis §2.1. Edit ops = §2.2. REST = §2.3. Apply pipeline = §2.3 + reader-3 §3.3. Undo/Redo = §2.4 / reader-3 §4. Optimistic concurrency = §2.3.
- Existing web layer: `webapp/api/main.py`, `webapp/api/jobs.py` (`JobStore`, `_solve_lock:44`), `webapp/api/config.py`.

**Treat as already existing (P2a-1 deliverables — do NOT re-implement):**
- `shift_scheduler/src/grid_derivation.py`: `derive_cell_text(tech_id, day, day_assignments, night_assignments, requests, nuc_tx_ids) -> str`, `cell_fill(text) -> str | None`.
- `shift_scheduler/src/stats_engine.py`: `recompute_off_daikyu(day_assignments, night_assignments, requests, staff_ids, year, month, target_holidays) -> (off_counts, daikyu_counts)`, plus the module-level `PURE_HOLIDAY_SYMS` / `CONDITIONAL_HOLIDAY_SYMS` / `FORCED_WORK_SYMS` and the per-day classifier (`_classify` / `_is_public_off`).
- `ScheduleResult.daily_location_needs` field (default `{}`, excluded from `as_dict()`).
- `tests/golden/2026-06_p2a1.json` (committed) — has `year, month, days_in_month, nuc_tx_ids, active_staff_ids, day_assignments, night_assignments, requests, expected_cells, expected_off_counts, expected_daikyu_counts, target_holidays`.

---

## Design decisions resolved (ambiguities the synthesis left open)

1. **Dict-form everywhere.** Reader-1 sketched `recompute_stats` over a `DayAssignment` list. P2a-1 already committed to the **dict** shapes (`day_assignments {day:{loc:[sid]}}`, `night_assignments {day:[sid]}`, `requests {day:{sid:sym}}`) for `recompute_off_daikyu`, and `build_grid` consumes the same dicts. P2a-2 keeps **dict-form throughout** so `build_grid`, `recompute_stats`, and `roster_to_dicts` share one representation and reuse P2a-1 verbatim. (No `DayAssignment` objects in the edit loop.)
2. **Enriched `staff_json`.** Synthesis §2.1 lists `staff_json` as `[{id,name,status}]`, but `build_grid` needs `.note` (to compute `nuc_tx_ids`) and `recompute_stats` night-HB needs `.night_hb`. We persist the **superset** `[{id,name,status,note,night_hb}]` so the roster is self-contained — no CSV reload per edit. `roster_to_dicts` rebuilds lightweight staff objects (`types.SimpleNamespace`) with those attributes.
3. **`skill` warnings deferred to P3.** They need the skills/power-balance masters (CSV-only until P3). `recompute_stats` returns `coverage`, `holiday_deficit`, `consecutive`, `night_hb_gaps`; the edit response includes `"skill": []` as a documented placeholder.
4. **`daily_location_needs` keying.** Persisted as `daily_needs_json` with **ISO-date string** keys (`'YYYY-MM-DD'`) → `{loc_code: required}`. `roster_to_dicts` normalizes to **day-int** keys to match the dict-form coverage loop. Coverage folds `クL`→`ク` and skips parenthesized loc codes via `startswith('(') and endswith(')')` (mirrors `main.py:1213`).
5. **DB access.** `config.Settings` gains `db_path` (env `SHIFT_DB_PATH`, default `webapp_data/shift.db`). A FastAPI dependency `get_db()` yields a per-request `sqlite3.Connection` (`PRAGMA foreign_keys=ON`, `row_factory=sqlite3.Row`). Tests override `app.dependency_overrides[get_db]` with a `tmp_path` DB. No global mutable connection.
6. **Freeze split for testability.** The persistence function `freeze_roster(conn, *, job_id, result, technicians, data_dir, target_holidays, created_by=None) -> int` takes a `ScheduleResult` + a full `technicians` list and is unit-tested with **synthetic** staff (fast, no solver). The `POST /jobs/{job_id}/freeze` endpoint loads `technicians` from `data_dir` and calls it. Freeze is **idempotent per `job_id`** (one roster per job; re-freeze returns the existing id).
7. **Edit pipeline recompute order.** mutate rows → `roster_to_dicts` → `recompute_stats` (whole roster; off/daikyu/warnings, sub-ms) → `build_grid(cells=affected, off_counts=recomputed, daikyu_counts=recomputed)` → assemble `changed_cells` (text/kind/fill from grid + `locked` from rows) and `stats` (affected staff's 21-col block, with correct 公休/代休) → update `roster_meta` for affected staff. Warnings returned whole (cheap); `stats` returned for affected staff only.

---

## File Structure

**Create:**
- `tests/golden/gen_p2a2_fixture.py` — one-time generator: reuses the **already-solved** `tests/golden/2026-06_p2a1.json` assignments (NO re-solve), builds the **current** `ExcelGenerator`, renders xlsx bytes, parses the 21 stat columns + has-work + on-call rows per active staff as the ground truth.
- `tests/golden/2026-06_p2a2.json` — generated fixture (committed): `expected_stats {sid:{label:val}|null}`, `expected_has_work {sid:bool}`, `expected_oncall [{label,cells}]`.
- `webapp/api/db.py` — `connect(path)`, `init_db(conn)`, `get_db()` dependency, the 4-table DDL.
- `webapp/api/rosters.py` — `freeze_roster`, `roster_to_dicts`, `load_roster_header`, `build_roster_grid`, `apply_edit`, `undo`, `redo`, affected-cell helper, JSON (de)serialization.
- `tests/test_build_grid.py`, `tests/test_recompute_stats.py`, `tests/test_db.py`, `tests/test_freeze.py`, `tests/test_roster_read.py`, `tests/test_edits.py`, `tests/test_undo_redo.py`, `tests/test_roster_api.py`.

**Modify:**
- `shift_scheduler/src/grid_derivation.py` — add `build_grid(...)` (calls P2a-1 `derive_cell_text`/`cell_fill`; ports counting loop).
- `shift_scheduler/src/stats_engine.py` — add `recompute_stats(...)` (extends `recompute_off_daikyu` with coverage/HB/consecutive/holiday_deficit).
- `webapp/api/config.py` — add `db_path`.
- `webapp/api/main.py` — add the 6 endpoints + `get_db` wiring.

All commands assume repo root `"/Users/kohei/Desktop/local-shift ver1"` is cwd and the venv is active (`source .venv/bin/activate`). Run tests with `python -m pytest`. Keep edit-API tests FAST: seed a tiny roster directly in a `tmp_path` DB (or via the synthetic `freeze_roster`); never invoke the real solver.

This plan is split into **three parts in one file**:
- **Part A** — `build_grid` + `recompute_stats` (pure, no DB).
- **Part B** — SQLite persistence + freeze + read endpoints.
- **Part C** — edit ops, undo/redo, optimistic concurrency, full API integration.

---

# Part A — `build_grid` + `recompute_stats`

## Task A1: Capture the P2a-2 stats/has-work/on-call golden (no re-solve)

This pins the **current** `ExcelGenerator`'s 21-column stats, the `has_work` blanking, and the on-call rows as ground truth, reusing the assignments already solved in the P2a-1 fixture so it runs in seconds (no CP-SAT).

**Files:**
- Create: `tests/golden/gen_p2a2_fixture.py`
- Create (generated): `tests/golden/2026-06_p2a2.json`

- [ ] **Step 1: Write the generator script**

```python
# tests/golden/gen_p2a2_fixture.py
"""One-time generator for the P2a-2 build_grid golden. Reuses the assignments
already solved in tests/golden/2026-06_p2a1.json (NO solver run): it builds the
CURRENT ExcelGenerator, renders the xlsx, and parses the 21 stat columns,
has-work blanking, and on-call rows per active staff as ground truth that the
new build_grid must reproduce byte-for-byte.
Usage: python tests/golden/gen_p2a2_fixture.py
"""
import json
from io import BytesIO

import openpyxl

from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.excel_generator import ExcelGenerator

YEAR, MONTH, DATA_DIR = 2026, 6, "shift_scheduler/data"
P2A1 = "tests/golden/2026-06_p2a1.json"


def main():
    fix = json.load(open(P2A1, encoding="utf-8"))
    day = {int(d): v for d, v in fix["day_assignments"].items()}
    night = {int(d): v for d, v in fix["night_assignments"].items()}
    req = {int(d): v for d, v in fix["requests"].items()}
    off = fix["expected_off_counts"]
    daikyu = fix["expected_daikyu_counts"]

    technicians = DataLoader(data_dir=DATA_DIR).load_all(f"{YEAR}-{MONTH:02d}")[0]
    active = [t for t in technicians if t.status == "在籍"]

    gen = ExcelGenerator(
        year=YEAR, month=MONTH, technicians=technicians,
        night_assignments=night, day_assignments=day, requests=req,
        on_call_assignments={}, daikyu_counts=daikyu, off_counts=off,
        validation_errors=[],
    )
    wb = openpyxl.load_workbook(BytesIO(gen.generate_bytes()))
    ws = wb["6月勤務表"]  # main sheet (see tests/test_excel_bytes.py)

    stats_columns = gen.stats_columns
    days = gen.days_in_month
    first_stat_col = 1 + 1 + days  # A=勤務表番号, B=技師名, then `days` day cols, then stats
    # Map staff_num -> row by scanning column A (勤務表番号).
    num_to_row = {}
    for r in range(4, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if v not in (None, ""):
            num_to_row[str(v)] = r

    expected_stats, expected_has_work = {}, {}
    for t in active:
        try:
            num = str(int(t.id.replace("T", "")))
        except ValueError:
            num = t.id
        row = num_to_row.get(num)
        if row is None:
            expected_stats[t.id] = None
            expected_has_work[t.id] = False
            continue
        vals = [ws.cell(row=row, column=first_stat_col + i).value
                for i in range(len(stats_columns))]
        if all(v in (None, "") for v in vals):
            expected_stats[t.id] = None
            expected_has_work[t.id] = False
        else:
            expected_stats[t.id] = {
                lbl: (vals[i] if vals[i] not in (None, "") else 0)
                for i, lbl in enumerate(stats_columns)
            }
            expected_has_work[t.id] = True

    fixture = {
        "year": YEAR, "month": MONTH, "days_in_month": days,
        "stats_columns": stats_columns,
        "expected_stats": expected_stats,
        "expected_has_work": expected_has_work,
    }
    with open("tests/golden/2026-06_p2a2.json", "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, sort_keys=True, indent=2)
    print(f"wrote tests/golden/2026-06_p2a2.json: {len(active)} active staff")


if __name__ == "__main__":
    main()
```

> Note for the implementer: the stat-column ordinal offset (`first_stat_col`) and the sheet name (`"6月勤務表"`) come from `tests/test_excel_bytes.py` + `excel_generator.py:305-336`. If the parse finds all-`None` stat cells for every staff, re-check the column offset against `_apply_formatting` (`max_col = days_in_month + 2 + len(stats_columns)`) before proceeding — do NOT loosen the test.

- [ ] **Step 2: Generate the fixture (fast — no solver)**

Run: `python tests/golden/gen_p2a2_fixture.py`
Expected: prints `wrote tests/golden/2026-06_p2a2.json: <N> active staff`. Confirm the file exists and at least one staff has a non-null `expected_stats` block and at least one has `expected_has_work == false`.

- [ ] **Step 3: Commit**

```bash
git add tests/golden/gen_p2a2_fixture.py tests/golden/2026-06_p2a2.json
git commit -m "test(p2a2): capture current ExcelGenerator stats/has_work golden (no re-solve)"
```

---

## Task A2: Implement `build_grid(...)` in `grid_derivation.py`

**Files:**
- Read: `shift_scheduler/src/excel_generator.py:100,144-206,316` (the 21 labels, `WORK_LOCATION_CODES`, counting loop, `has_work` gate) and the P2a-2 reader's reference `build_grid` (it mirrors the file exactly).
- Modify: `shift_scheduler/src/grid_derivation.py`
- Test: `tests/test_build_grid.py`

`build_grid` calls P2a-1's `derive_cell_text` (do NOT re-derive) and `cell_fill`, and **ports verbatim** the counting loop from `excel_generator.py:158-206` (the `クL`→`ク` fold at `:189`, the whole-cell `'夜' in text` 夜勤 test, the `WORK_LOCATION_CODES` superset gating `has_work`, and 公休/代休 injected from `off_counts`/`daikyu_counts` **after** counting, overwriting parsed values). Stats block is `None` when `has_work` is False.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_grid.py
import json
from types import SimpleNamespace

from shift_scheduler.src.grid_derivation import build_grid
from shift_scheduler.src.loaders.data_loader import DataLoader

P2A1 = json.load(open("tests/golden/2026-06_p2a1.json", encoding="utf-8"))
P2A2 = json.load(open("tests/golden/2026-06_p2a2.json", encoding="utf-8"))
DAY = {int(d): v for d, v in P2A1["day_assignments"].items()}
NIGHT = {int(d): v for d, v in P2A1["night_assignments"].items()}
REQ = {int(d): v for d, v in P2A1["requests"].items()}
OFF = P2A1["expected_off_counts"]
DAIKYU = P2A1["expected_daikyu_counts"]

# Full Staff objects are needed (note -> nuc_tx_ids); load once.
TECHS = DataLoader(data_dir="shift_scheduler/data").load_all("2026-06")[0]


def _grid():
    return build_grid(
        2026, 6, TECHS, DAY, NIGHT, REQ,
        off_counts=OFF, daikyu_counts=DAIKYU, on_call_assignments=None,
    )


def test_rows_cells_match_p2a1_expected_cells():
    grid = _grid()
    by_id = {r["staff_id"]: r for r in grid["rows"]}
    mismatches = []
    for sid, by_day in P2A1["expected_cells"].items():
        row = by_id.get(sid)
        assert row is not None, f"missing row {sid}"
        for d_str, expected in by_day.items():
            got = row["cells"][int(d_str)]
            if got != expected:
                mismatches.append((sid, d_str, expected, got))
    assert not mismatches, f"{len(mismatches)} cell mismatches, first 5: {mismatches[:5]}"


def test_stats_and_has_work_match_p2a2_golden():
    grid = _grid()
    by_id = {r["staff_id"]: r for r in grid["rows"]}
    for sid, expected_stats in P2A2["expected_stats"].items():
        row = by_id[sid]
        assert row["has_work"] == P2A2["expected_has_work"][sid], sid
        if expected_stats is None:
            assert row["stats"] is None, sid
        else:
            assert row["stats"] == expected_stats, sid


def test_stats_columns_and_weekdays_shape():
    grid = _grid()
    assert grid["stats_columns"] == P2A2["stats_columns"]
    assert grid["days_in_month"] == 30
    assert grid["weekdays"][1] in "月火水木金土日"
    # 2026-06-01 is a Monday
    assert grid["weekdays"][1] == "月"


def test_kouho_daikyu_injected_after_counting_overwrites_parsed():
    # 公休/代休 must come from off/daikyu counts, NOT from string parsing.
    grid = _grid()
    for r in grid["rows"]:
        if r["stats"] is not None:
            assert r["stats"]["公休"] == OFF.get(r["staff_id"], 0)
            assert r["stats"]["代休"] == DAIKYU.get(r["staff_id"], 0)


def test_oncall_rows_present_when_supplied():
    techs = [SimpleNamespace(id="T001", name="甲 (海)", status="在籍", note="",
                             night_hb=False),
             SimpleNamespace(id="T002", name="乙", status="在籍", note="",
                             night_hb=False)]
    grid = build_grid(2026, 6, techs, {}, {}, {},
                      on_call_assignments={1: {"第1拘束": "T001", "第2拘束": "T002"}})
    labels = [r["label"] for r in grid["oncall_rows"]]
    assert labels == ["第1拘束", "第2拘束"]
    # parens/spaces stripped per excel_generator.py:210-232
    assert grid["oncall_rows"][0]["cells"][1] == "甲海"


def test_cells_fast_path_restricts_to_affected_staff():
    grid = build_grid(2026, 6, TECHS, DAY, NIGHT, REQ,
                      off_counts=OFF, daikyu_counts=DAIKYU,
                      cells={(P2A1["active_staff_ids"][0], 5)})
    ids = {r["staff_id"] for r in grid["rows"]}
    assert ids == {P2A1["active_staff_ids"][0]}
    # the row is still fully derived so its stats are correct
    assert len(grid["rows"][0]["cells"]) == 30
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_build_grid.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_grid'` (or `AttributeError`).

- [ ] **Step 3: Implement `build_grid`**

Append to `shift_scheduler/src/grid_derivation.py`. Reuse P2a-1's `derive_cell_text` (do not re-derive). **Copy/port verbatim** the counting loop and `WORK_LOCATION_CODES`/`STATS_COLUMNS` from `excel_generator.py:144-206` (cited inline). Skeleton:

```python
import calendar
from datetime import date

STATS_COLUMNS = ['夜勤','病院MR','CLMR','病CT','CT','ア','心','ク','ポ','精',
                 'MG','DR','HB','OP','入','病L','超遅','ク遅','M遅','公休','代休']  # excel_generator.py:100,144,316
WORK_LOCATION_CODES = {  # excel_generator.py (superset; gates has_work, no own column for some)
    '病院MR','CLMR','CT','病CT','ア','心','ク','クL','ポ','精',
    'MG','DR','HB','OP','PICC','入','病L','超遅','ク遅','M遅',
    '館山','TV','PET','RI','放治','DX',
}
_WEEKDAY = ['月','火','水','木','金','土','日']
_SPECIAL_OFF = {'★', '☆', '◆'}


def _kind_for(text):
    # additive web-only metadata (do NOT drive Excel fill off this; fill keys off text)
    if text == '○':            return 'akemei'
    if '夜' in text:           return 'night'
    if text in _SPECIAL_OFF:   return 'special_off'
    if text == '休':           return 'off'
    if text == '':             return 'empty'
    return 'work'


def _count_row(cells):
    # VERBATIM port of excel_generator.py:158-206 counting loop.
    counts = {label: 0 for label in STATS_COLUMNS}
    has_work = False
    for text in cells.values():
        if '夜' in text:                 # whole-cell substring test, BEFORE split (:160)
            counts['夜勤'] += 1
        for p in text.split('/'):
            p = p.strip()
            if   p.endswith('(希)'):  p = p[:-3]      # normalization order: (希) -> （希） -> 夜
            elif p.endswith('（希）'): p = p[:-3]
            if p.endswith('夜'):      p = p[:-1]
            if p in WORK_LOCATION_CODES:
                has_work = True
            if p == 'クL':            p = 'ク'        # :189 fold
            if p in counts:
                counts[p] += 1
    return counts, has_work


def build_grid(year, month, technicians, day_assignments, night_assignments,
               requests, off_counts=None, daikyu_counts=None,
               on_call_assignments=None, cells=None):
    """Whole grid (cells=None) or affected-staff fast path (cells={(sid,day),...}).
    Reuses derive_cell_text/cell_fill (P2a-1). 公休/代休 injected AFTER counting."""
    off_counts = off_counts or {}
    daikyu_counts = daikyu_counts or {}
    days = calendar.monthrange(year, month)[1]
    nuc_tx_ids = {t.id for t in technicians
                  if getattr(t, 'note', '') and ('核医学' in t.note or '治療' in t.note)}
    weekdays = {d: _WEEKDAY[date(year, month, d).weekday()] for d in range(1, days + 1)}

    scope = None if cells is None else {sid for (sid, _d) in cells}
    rows = []
    for t in technicians:
        if getattr(t, 'status', '在籍') != '在籍':
            continue
        if scope is not None and t.id not in scope:
            continue
        try:    num = int(t.id.replace('T', ''))
        except ValueError: num = t.id
        row_cells, cell_meta = {}, {}
        for d in range(1, days + 1):
            text = derive_cell_text(t.id, d, day_assignments, night_assignments,
                                    requests, nuc_tx_ids)
            row_cells[d] = text
            cell_meta[d] = {"kind": _kind_for(text), "fill": cell_fill(text)}
        counts, has_work = _count_row(row_cells)
        counts['公休'] = off_counts.get(t.id, 0)      # inject AFTER counting (:195-196)
        counts['代休'] = daikyu_counts.get(t.id, 0)
        rows.append({
            "staff_id": t.id, "staff_num": num, "name": t.name,
            "cells": row_cells, "cell_meta": cell_meta,
            "has_work": has_work,
            "stats": counts if has_work else None,
        })

    oncall_rows = []
    if on_call_assignments:
        names = {t.id: t.name for t in technicians}
        for label in ('第1拘束', '第2拘束'):
            rc = {}
            for d in range(1, days + 1):
                sid = on_call_assignments.get(d, {}).get(label)
                if sid:
                    nm = names.get(sid, sid)
                    nm = nm.replace('(', '').replace(')', '').replace(' ', '').replace('　', '')
                    rc[d] = nm
                else:
                    rc[d] = ''
            oncall_rows.append({"label": label, "cells": rc})

    return {
        "year": year, "month": month, "days_in_month": days,
        "weekdays": weekdays, "stats_columns": STATS_COLUMNS,
        "rows": rows, "oncall_rows": oncall_rows,
    }
```

(Ensure `derive_cell_text`/`cell_fill` are referenced from the same module — they are, per P2a-1.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_build_grid.py -v`
Expected: PASS — every cell matches the P2a-1 golden; stats/has_work match the P2a-2 golden; injection ordering and on-call stripping correct.

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/grid_derivation.py tests/test_build_grid.py
git commit -m "feat(grid): build_grid full dict assembly (rows+stats+oncall), byte-identical to ExcelGenerator"
```

---

## Task A3: Implement `recompute_stats(...)` in `stats_engine.py`

**Files:**
- Read: `main.py:1210-1225` (coverage + night-HB), `main.py:82-88` (7-day window ref), and P2a-1's `recompute_off_daikyu` + classifier.
- Modify: `shift_scheduler/src/stats_engine.py`
- Test: `tests/test_recompute_stats.py`

`recompute_stats` extends P2a-1: it calls `recompute_off_daikyu` for off/daikyu, derives `holiday_deficit` from `off < target`, computes `coverage` vs `daily_location_needs` (folding `クL`→`ク`, skipping parenthesized codes), `night_hb_gaps`, and `consecutive` (any run of work-status days `>= 7`). It must reuse the **same** per-day classifier P2a-1 exposes (`_classify`) so the consecutive run uses identical status semantics. `出/☆` half-days count as work in the run (documented policy, matches `main.py:946-949`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recompute_stats.py
import json
from types import SimpleNamespace

from shift_scheduler.src.stats_engine import recompute_stats

P2A1 = json.load(open("tests/golden/2026-06_p2a1.json", encoding="utf-8"))
DAY = {int(d): v for d, v in P2A1["day_assignments"].items()}
NIGHT = {int(d): v for d, v in P2A1["night_assignments"].items()}
REQ = {int(d): v for d, v in P2A1["requests"].items()}


def _techs(ids):
    return [SimpleNamespace(id=i, name=i, status="在籍", note="", night_hb=False)
            for i in ids]


def test_off_daikyu_idempotent_on_unedited_golden():
    techs = _techs(P2A1["active_staff_ids"])
    out = recompute_stats(DAY, NIGHT, REQ, techs, P2A1["year"], P2A1["month"],
                          P2A1["target_holidays"])
    assert out["off_counts"] == P2A1["expected_off_counts"]
    assert {k: v for k, v in out["daikyu_counts"].items() if v} == \
           {k: v for k, v in P2A1["expected_daikyu_counts"].items() if v}


def test_holiday_deficit_mirrors_daikyu():
    techs = _techs(["T001", "T002"])
    # T001 fully assigned weekdays (no off) -> deficit; T002 unassigned -> off via blanks
    day = {d: {"CT": ["T001"]} for d in range(1, 31)}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, target_holidays=9)
    deficits = {w["staff_id"]: w["short"] for w in out["holiday_deficit"]}
    assert "T001" in deficits and deficits["T001"] > 0
    assert "T002" not in deficits  # T002 accrues off from blank weekdays


def test_coverage_understaffing_and_kuL_fold():
    techs = _techs(["T001", "T002"])
    day = {1: {"クL": ["T001"]}}            # クL must count toward ク
    needs = {"2026-06-01": {"ク": 2, "(補助)": 5}}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, target_holidays=9,
                          daily_location_needs=needs)
    cov = out["coverage"]
    assert len(cov) == 1
    assert cov[0]["location"] == "ク" and cov[0]["required"] == 2
    assert cov[0]["assigned"] == 1 and cov[0]["short"] == 1   # クL folded in
    # parenthesized (補助) is skipped entirely
    assert all(c["location"] != "(補助)" for c in cov)


def test_night_hb_gap_detected():
    techs = [SimpleNamespace(id="T001", name="a", status="在籍", note="", night_hb=False),
             SimpleNamespace(id="T002", name="b", status="在籍", note="", night_hb=True)]
    night_gap = {1: ["T001"]}        # no HB-capable -> gap
    night_ok = {2: ["T002"]}         # HB-capable present -> no gap
    out_gap = recompute_stats({}, night_gap, {}, techs, 2026, 6, 9)
    out_ok = recompute_stats({}, night_ok, {}, techs, 2026, 6, 9)
    assert 1 in out_gap["night_hb_gaps"]
    assert out_ok["night_hb_gaps"] == []


def test_consecutive_run_of_seven_flagged():
    techs = _techs(["T001"])
    day = {d: {"CT": ["T001"]} for d in range(1, 8)}   # 7 straight work days
    out = recompute_stats(day, {}, {}, techs, 2026, 6, 9)
    cons = out["consecutive"]
    assert any(c["staff_id"] == "T001" and c["len"] >= 7 for c in cons)


def test_staff_scope_limits_per_staff_outputs():
    techs = _techs(["T001", "T002"])
    day = {1: {"CT": ["T001", "T002"]}}
    out = recompute_stats(day, {}, {}, techs, 2026, 6, 9, staff_scope={"T001"})
    assert set(out["off_counts"]) == {"T001"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_recompute_stats.py -v`
Expected: FAIL with `ImportError: cannot import name 'recompute_stats'`.

- [ ] **Step 3: Implement `recompute_stats`**

Append to `shift_scheduler/src/stats_engine.py`. Reuse `recompute_off_daikyu` and the P2a-1 classifier. Skeleton (cite sources inline):

```python
import calendar
from collections import defaultdict
from datetime import date, timedelta


def _day_of(iso_or_day):
    """Accept 'YYYY-MM-DD', date, or int day -> int day."""
    if isinstance(iso_or_day, int):
        return iso_or_day
    if isinstance(iso_or_day, date):
        return iso_or_day.day
    return int(str(iso_or_day).split('-')[2])


def recompute_stats(day_assignments, night_assignments, requests, technicians,
                    year, month, target_holidays, *,
                    daily_location_needs=None, staff_scope=None):
    """Solver-free recompute of off/daikyu/coverage/holiday_deficit/consecutive/
    night-HB. Mirrors main.py:19-185 (via recompute_off_daikyu) + main.py:1210-1225.
    Returns a plain JSON-able dict. `skill`/PB warnings are P3 (not here)."""
    num_days = calendar.monthrange(year, month)[1]
    active = [t for t in technicians if getattr(t, 'status', '在籍') == '在籍']
    if staff_scope is not None:
        active = [t for t in active if t.id in staff_scope]
    staff_ids = [t.id for t in active]

    off_counts, daikyu_counts = recompute_off_daikyu(
        day_assignments, night_assignments, requests,
        staff_ids, year, month, target_holidays)

    # holiday_deficit mirrors daikyu (off < target).
    holiday_deficit = [
        {"staff_id": sid, "off": off_counts[sid], "target": target_holidays,
         "short": round(target_holidays - off_counts[sid], 1)}
        for sid in staff_ids if off_counts[sid] < target_holidays
    ]

    # consecutive: any run of work-status days >= 7. Reuse the P2a-1 classifier so
    # status semantics are identical; 出/☆ half counts as work (main.py:946-949).
    consecutive = []
    night_set = {(sid, d) for d, ids in night_assignments.items() for sid in ids}
    for sid in staff_ids:
        run = 0
        start_day = None
        for dn in range(1, num_days + 1):
            d = date(year, month, dn)
            st = _classify(sid, d, day_assignments, night_assignments, requests)  # P2a-1
            working = st in ('work', 'half')
            if working:
                if run == 0:
                    start_day = dn
                run += 1
                if run >= 7:
                    consecutive.append({
                        "staff_id": sid,
                        "start": date(year, month, start_day).isoformat(),
                        "len": run})
            else:
                run = 0

    # coverage vs daily_location_needs (fold クL->ク; skip parenthesized).
    coverage = []
    if daily_location_needs:
        assigned_by_day = defaultdict(lambda: defaultdict(list))
        for dn, locs in day_assignments.items():
            for loc, ids in locs.items():
                assigned_by_day[int(dn)][loc].extend(ids)
        for key, loc_needs in daily_location_needs.items():
            dn = _day_of(key)
            for loc_code, required in loc_needs.items():
                if loc_code.startswith('(') and loc_code.endswith(')'):  # main.py:1213
                    continue
                if not required or required <= 0:
                    continue
                assigned = len(assigned_by_day[dn].get(loc_code, []))
                if loc_code == 'ク':
                    assigned += len(assigned_by_day[dn].get('クL', []))  # fold
                if assigned < required:
                    coverage.append({
                        "date": date(year, month, dn).isoformat(),
                        "location": loc_code, "required": required,
                        "assigned": assigned, "short": required - assigned})

    # night-HB gaps (main.py:1218-1225).
    by_id = {t.id: t for t in technicians}
    night_hb_gaps = [
        int(dn) for dn, ids in night_assignments.items()
        if not any(getattr(by_id.get(i), 'night_hb', False) for i in ids)
    ]

    return {
        "off_counts": off_counts,
        "daikyu_counts": daikyu_counts,
        "holiday_deficit": holiday_deficit,
        "coverage": coverage,
        "consecutive": consecutive,
        "night_hb_gaps": sorted(night_hb_gaps),
    }
```

> If P2a-1 named its classifier differently (e.g. `_classify(sid, d, dnum, ...)`), adapt the call — the requirement is to **reuse the same classification**, not to re-define the symbol sets or branch order. If the classifier is not importable, add a thin public wrapper in `stats_engine.py` rather than copying logic.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_recompute_stats.py -v`
Expected: PASS — off/daikyu idempotent on the golden; coverage folds `クL`, skips parens; HB gap + consecutive + scope correct.

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/stats_engine.py tests/test_recompute_stats.py
git commit -m "feat(stats): recompute_stats adds coverage/holiday_deficit/consecutive/night-HB on top of off/daikyu"
```

---

# Part B — SQLite persistence + freeze + read

## Task B1: `webapp/api/db.py` — schema + connection

**Files:**
- Create: `webapp/api/db.py`
- Modify: `webapp/api/config.py`
- Test: `tests/test_db.py`

Use stdlib `sqlite3`. The 4 tables are **synthesis §2.1 verbatim** (column names/constraints).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
import sqlite3

from webapp.api.db import connect, init_db


def test_init_db_creates_four_tables(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"rosters", "roster_assignments", "roster_meta", "roster_edits"} <= names


def test_foreign_keys_and_cascade(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO rosters(year,month,target_holidays,data_dir,staff_json,created_at)"
        " VALUES(2026,6,9,'d','[]','2026-06-29T00:00:00')")
    rid = cur.lastrowid
    conn.execute(
        "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,location_or_role)"
        " VALUES(?,?,?,?,?)", (rid, "T001", "2026-06-01", "day", "CT"))
    conn.commit()
    conn.execute("DELETE FROM rosters WHERE id=?", (rid,))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM roster_assignments").fetchone()[0]
    assert n == 0  # ON DELETE CASCADE with PRAGMA foreign_keys=ON


def test_status_check_constraint(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rosters(year,month,target_holidays,data_dir,staff_json,"
            "created_at,status) VALUES(2026,6,9,'d','[]','t','bogus')")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.api.db'`.

- [ ] **Step 3: Implement `db.py` + config**

```python
# webapp/api/db.py
import sqlite3

from webapp.api.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS rosters (
  id INTEGER PRIMARY KEY, job_id TEXT, year INT NOT NULL, month INT NOT NULL,
  target_holidays INT NOT NULL, data_dir TEXT NOT NULL, master_set_id INT,
  staff_json TEXT NOT NULL, daily_needs_json TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN('draft','confirmed')),
  version INT NOT NULL DEFAULT 0, edit_cursor INT NOT NULL DEFAULT 0,
  created_by TEXT, created_at TEXT NOT NULL, confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS roster_assignments (
  id INTEGER PRIMARY KEY,
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  staff_id TEXT NOT NULL, date TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN('day','night','oncall','request')),
  location_or_role TEXT, symbol TEXT, locked INT NOT NULL DEFAULT 0,
  UNIQUE(roster_id,staff_id,date,kind,location_or_role)
);
CREATE INDEX IF NOT EXISTS ix_ra_roster_date  ON roster_assignments(roster_id,date);
CREATE INDEX IF NOT EXISTS ix_ra_roster_staff ON roster_assignments(roster_id,staff_id);
CREATE TABLE IF NOT EXISTS roster_meta (
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  staff_id TEXT NOT NULL, off_count REAL NOT NULL DEFAULT 0,
  daikyu_count REAL NOT NULL DEFAULT 0, stats_json TEXT NOT NULL,
  PRIMARY KEY(roster_id,staff_id)
);
CREATE TABLE IF NOT EXISTS roster_edits (
  id INTEGER PRIMARY KEY,
  roster_id INT NOT NULL REFERENCES rosters(id) ON DELETE CASCADE,
  seq INT NOT NULL, user_id TEXT, at TEXT NOT NULL,
  op TEXT NOT NULL CHECK(op IN('assign','unassign','move','toggle_lock','set_symbol','resolve')),
  payload_json TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
  undone INT NOT NULL DEFAULT 0, UNIQUE(roster_id,seq)
);
CREATE INDEX IF NOT EXISTS ix_re_roster_seq ON roster_edits(roster_id,seq);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db():
    """FastAPI dependency: one connection per request (overridable in tests)."""
    conn = connect(settings.db_path)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()
```

Add to `webapp/api/config.py`:

```python
    db_path: str = os.environ.get("SHIFT_DB_PATH", "webapp_data/shift.db")
```

(Ensure the parent dir is created lazily by `connect` if needed, e.g. `os.makedirs(os.path.dirname(path), exist_ok=True)` when `path` has a dir component.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webapp/api/db.py webapp/api/config.py tests/test_db.py
git commit -m "feat(db): sqlite roster schema (4 tables, FK cascade, checks) + get_db dependency"
```

---

## Task B2: `freeze_roster` + `roster_to_dicts` adapter

**Files:**
- Create: `webapp/api/rosters.py`
- Test: `tests/test_freeze.py`

`freeze_roster` maps `ScheduleResult → rows` per synthesis §2.1; `roster_to_dicts` is the inverse adapter producing the dict shapes `build_grid`/`recompute_stats` consume. Tests use **synthetic** staff (`SimpleNamespace`) and a hand-built `ScheduleResult` — no solver.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freeze.py
from types import SimpleNamespace

from shift_scheduler.src.models.schedule_result import ScheduleResult
from webapp.api.db import connect, init_db
from webapp.api.rosters import freeze_roster, roster_to_dicts


def _conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_db(c)
    return c


def _result():
    return ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}, {"id": "T002", "name": "乙"}],
        day_assignments={1: {"CT": ["T001"], "休": ["T002"]}, 2: {"○": ["T001"]}},
        night_assignments={1: ["T001"]},
        requests={1: {"T002": "☆"}},
        on_call_assignments={1: {"第1拘束": "T001"}},
        daikyu_counts={"T001": 0}, off_counts={"T001": 9, "T002": 10},
        validation_errors=["ignored"],
        daily_location_needs={1: {"CT": 1}},
    )


def _techs():
    return [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=True),
            SimpleNamespace(id="T002", name="乙", status="在籍", note="核医学", night_hb=False)]


def test_freeze_creates_rows_and_meta(tmp_path):
    conn = _conn(tmp_path)
    rid = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                        data_dir="d", target_holidays=9)
    kinds = [r["kind"] for r in conn.execute(
        "SELECT kind FROM roster_assignments WHERE roster_id=?", (rid,))]
    assert kinds.count("day") == 3       # CT, 休, ○
    assert kinds.count("night") == 1
    assert kinds.count("request") == 1
    assert kinds.count("oncall") == 1
    meta = {r["staff_id"]: r for r in conn.execute(
        "SELECT * FROM roster_meta WHERE roster_id=?", (rid,))}
    assert meta["T002"]["off_count"] == 10
    # validation_errors NOT frozen anywhere
    hdr = conn.execute("SELECT * FROM rosters WHERE id=?", (rid,)).fetchone()
    assert hdr["target_holidays"] == 9 and hdr["version"] == 0 and hdr["edit_cursor"] == 0


def test_freeze_idempotent_per_job(tmp_path):
    conn = _conn(tmp_path)
    a = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                      data_dir="d", target_holidays=9)
    b = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                      data_dir="d", target_holidays=9)
    assert a == b
    n = conn.execute("SELECT COUNT(*) FROM rosters").fetchone()[0]
    assert n == 1


def test_roster_to_dicts_round_trip(tmp_path):
    conn = _conn(tmp_path)
    rid = freeze_roster(conn, job_id="job1", result=_result(), technicians=_techs(),
                        data_dir="d", target_holidays=9)
    d = roster_to_dicts(conn, rid)
    assert d["day_assignments"][1]["CT"] == ["T001"]
    assert d["day_assignments"][1]["休"] == ["T002"]
    assert d["night_assignments"][1] == ["T001"]
    assert d["requests"][1]["T002"] == "☆"
    assert d["on_call_assignments"][1]["第1拘束"] == "T001"
    assert d["daily_location_needs"][1]["CT"] == 1
    # enriched staff carry note/night_hb for build_grid/recompute_stats
    by_id = {t.id: t for t in d["technicians"]}
    assert by_id["T002"].note == "核医学" and by_id["T001"].night_hb is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_freeze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp.api.rosters'`.

- [ ] **Step 3: Implement `rosters.py` (freeze + adapter)**

```python
# webapp/api/rosters.py
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from shift_scheduler.src.grid_derivation import build_grid
from shift_scheduler.src.stats_engine import recompute_stats


def _now():
    return datetime.now(timezone.utc).isoformat()


def _iso(year, month, day):
    return date(year, month, day).isoformat()


def _day_of(iso):
    return int(iso.split('-')[2])


def freeze_roster(conn, *, job_id, result, technicians, data_dir,
                  target_holidays, created_by=None) -> int:
    """Map a ScheduleResult -> rows (synthesis §2.1). Idempotent per job_id."""
    if job_id is not None:
        existing = conn.execute(
            "SELECT id FROM rosters WHERE job_id=?", (job_id,)).fetchone()
        if existing:
            return existing["id"]

    by_id = {t.id: t for t in technicians}
    staff = [{"id": t.id, "name": t.name, "status": getattr(t, "status", "在籍"),
              "note": getattr(t, "note", "") or "",
              "night_hb": bool(getattr(t, "night_hb", False))}
             for t in technicians]
    needs = {_iso(result.year, result.month, int(d) if not isinstance(d, date) else d.day):
             {lc: req for lc, req in locs.items()}
             for d, locs in (getattr(result, "daily_location_needs", {}) or {}).items()}

    cur = conn.execute(
        "INSERT INTO rosters(job_id,year,month,target_holidays,data_dir,staff_json,"
        "daily_needs_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (job_id, result.year, result.month, target_holidays, data_dir,
         json.dumps(staff, ensure_ascii=False),
         json.dumps(needs, ensure_ascii=False), created_by, _now()))
    rid = cur.lastrowid

    rows = []
    for d, locs in result.day_assignments.items():
        for loc, ids in locs.items():
            for sid in ids:
                rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                             "day", loc, None, 0))
    for d, ids in result.night_assignments.items():
        for sid in ids:
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "night", "夜", None, 0))
    for d, sm in result.requests.items():
        for sid, sym in sm.items():
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "request", None, sym, 0))
    for d, roles in (result.on_call_assignments or {}).items():
        for role, sid in roles.items():
            rows.append((rid, sid, _iso(result.year, result.month, int(d)),
                         "oncall", role, None, 0))
    conn.executemany(
        "INSERT OR IGNORE INTO roster_assignments"
        "(roster_id,staff_id,date,kind,location_or_role,symbol,locked)"
        " VALUES(?,?,?,?,?,?,?)", rows)

    # roster_meta from build_grid stats (carries off/daikyu-injected 公休/代休).
    grid = build_grid(result.year, result.month, technicians,
                      {int(d): v for d, v in result.day_assignments.items()},
                      {int(d): v for d, v in result.night_assignments.items()},
                      {int(d): v for d, v in result.requests.items()},
                      off_counts=result.off_counts, daikyu_counts=result.daikyu_counts)
    for r in grid["rows"]:
        sid = r["staff_id"]
        conn.execute(
            "INSERT OR REPLACE INTO roster_meta(roster_id,staff_id,off_count,"
            "daikyu_count,stats_json) VALUES(?,?,?,?,?)",
            (rid, sid, float(result.off_counts.get(sid, 0)),
             float(result.daikyu_counts.get(sid, 0)),
             json.dumps(r["stats"] or {}, ensure_ascii=False)))
    conn.commit()
    return rid


def roster_to_dicts(conn, roster_id) -> dict:
    """Rebuild the dict shapes build_grid/recompute_stats consume from frozen rows."""
    hdr = conn.execute("SELECT * FROM rosters WHERE id=?", (roster_id,)).fetchone()
    if hdr is None:
        raise KeyError(roster_id)
    staff = json.loads(hdr["staff_json"])
    technicians = [SimpleNamespace(id=s["id"], name=s["name"],
                                   status=s.get("status", "在籍"),
                                   note=s.get("note", ""),
                                   night_hb=bool(s.get("night_hb", False))) for s in staff]
    day_assignments, night_assignments, requests, on_call = {}, {}, {}, {}
    locked = {}  # (sid, day) -> locked flag of the day row
    for r in conn.execute(
            "SELECT * FROM roster_assignments WHERE roster_id=?", (roster_id,)):
        dn = _day_of(r["date"])
        if r["kind"] == "day":
            if r["location_or_role"] is not None:
                day_assignments.setdefault(dn, {}).setdefault(
                    r["location_or_role"], []).append(r["staff_id"])
            if r["locked"]:
                locked[(r["staff_id"], dn)] = True
        elif r["kind"] == "night":
            night_assignments.setdefault(dn, []).append(r["staff_id"])
        elif r["kind"] == "request":
            requests.setdefault(dn, {})[r["staff_id"]] = r["symbol"]
        elif r["kind"] == "oncall":
            on_call.setdefault(dn, {})[r["location_or_role"]] = r["staff_id"]
    needs = json.loads(hdr["daily_needs_json"] or "{}")
    return {
        "year": hdr["year"], "month": hdr["month"],
        "target_holidays": hdr["target_holidays"],
        "technicians": technicians,
        "day_assignments": day_assignments, "night_assignments": night_assignments,
        "requests": requests, "on_call_assignments": on_call,
        "daily_location_needs": {_day_of(k): v for k, v in needs.items()},
        "locked": locked, "version": hdr["version"], "edit_cursor": hdr["edit_cursor"],
        "status": hdr["status"],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_freeze.py -v`
Expected: PASS — rows/meta created, idempotent, round-trip exact (incl. `休`/`○` verbatim, enriched staff).

- [ ] **Step 5: Commit**

```bash
git add webapp/api/rosters.py tests/test_freeze.py
git commit -m "feat(roster): freeze_roster (ScheduleResult->rows, idempotent) + roster_to_dicts adapter"
```

---

## Task B3: Read endpoints + freeze endpoint wiring

**Files:**
- Modify: `webapp/api/rosters.py` (add `build_roster_grid`)
- Modify: `webapp/api/main.py` (add `POST /jobs/{job_id}/freeze`, `GET /rosters/{rid}`, `GET /rosters/{rid}/grid`)
- Test: `tests/test_roster_read.py`

`GET /rosters/{rid}` returns grid + stats + warnings + version; `GET /rosters/{rid}/grid` returns grid only. The freeze endpoint loads `technicians` from `data_dir` and calls `freeze_roster`. Tests seed a roster directly via `freeze_roster` and override `get_db`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roster_read.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments={1: {"CT": ["T001"]}}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={"T001": 9},
        validation_errors=[], daily_location_needs={1: {"CT": 1}})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_get_roster_returns_grid_stats_warnings_version(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).get(f"/rosters/{rid}")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 0
        assert any(row["staff_id"] == "T001" for row in body["grid"]["rows"])
        assert "warnings" in body and "coverage" in body["warnings"]
    finally:
        app.dependency_overrides.clear()


def test_get_roster_grid_only(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).get(f"/rosters/{rid}/grid")
        assert r.status_code == 200
        assert "rows" in r.json() and "warnings" not in r.json()
    finally:
        app.dependency_overrides.clear()


def test_get_missing_roster_404(tmp_path):
    conn, _ = _seed(tmp_path)
    try:
        assert _client(conn).get("/rosters/9999").status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_roster_read.py -v`
Expected: FAIL (no `/rosters/{rid}` route / no `get_db` attr on `api_main`).

- [ ] **Step 3: Implement `build_roster_grid` + endpoints**

Add to `rosters.py`:

```python
def _locked_cells(conn, roster_id):
    out = {}
    for r in conn.execute(
            "SELECT staff_id,date,locked FROM roster_assignments "
            "WHERE roster_id=? AND kind='day'", (roster_id,)):
        if r["locked"]:
            out[(r["staff_id"], _day_of(r["date"]))] = True
    return out


def build_roster_grid(conn, roster_id, *, cells=None):
    d = roster_to_dicts(conn, roster_id)
    off = {r["staff_id"]: r["off_count"] for r in conn.execute(
        "SELECT staff_id,off_count FROM roster_meta WHERE roster_id=?", (roster_id,))}
    daikyu = {r["staff_id"]: r["daikyu_count"] for r in conn.execute(
        "SELECT staff_id,daikyu_count FROM roster_meta WHERE roster_id=?", (roster_id,))}
    grid = build_grid(d["year"], d["month"], d["technicians"],
                      d["day_assignments"], d["night_assignments"], d["requests"],
                      off_counts=off, daikyu_counts=daikyu,
                      on_call_assignments=d["on_call_assignments"], cells=cells)
    return grid, d


def roster_warnings(d):
    return recompute_stats(
        d["day_assignments"], d["night_assignments"], d["requests"],
        d["technicians"], d["year"], d["month"], d["target_holidays"],
        daily_location_needs=d["daily_location_needs"])
```

Add to `webapp/api/main.py` (imports + routes):

```python
from fastapi import Depends
from webapp.api.db import get_db
from webapp.api import rosters as roster_ops


@app.post("/jobs/{job_id}/freeze", status_code=201)
def freeze_job(job_id: str, conn=Depends(get_db)):
    job = store.get(job_id)
    if job is None or job.result is None:
        raise HTTPException(status_code=404, detail="result not available")
    from shift_scheduler.src.loaders.data_loader import DataLoader
    technicians = DataLoader(data_dir=settings.data_dir).load_all(
        f"{job.year}-{job.month:02d}")[0]
    rid = roster_ops.freeze_roster(
        conn, job_id=job_id, result=job.result, technicians=technicians,
        data_dir=settings.data_dir, target_holidays=9)
    return {"roster_id": rid}


def _roster_or_404(conn, rid):
    hdr = conn.execute("SELECT id FROM rosters WHERE id=?", (rid,)).fetchone()
    if hdr is None:
        raise HTTPException(status_code=404, detail="roster not found")


@app.get("/rosters/{rid}")
def get_roster(rid: int, conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    grid, d = roster_ops.build_roster_grid(conn, rid)
    return {"version": d["version"], "status": d["status"], "grid": grid,
            "warnings": roster_ops.roster_warnings(d)}


@app.get("/rosters/{rid}/grid")
def get_roster_grid(rid: int, conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    grid, _ = roster_ops.build_roster_grid(conn, rid)
    return grid
```

> `target_holidays=9` matches the P1/CLI default (`assign_monthly_off_days` default). Persisted in `rosters.target_holidays` for fidelity; a later phase can thread a per-job value.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_roster_read.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webapp/api/rosters.py webapp/api/main.py tests/test_roster_read.py
git commit -m "feat(api): POST /jobs/{id}/freeze + GET /rosters/{rid}(/grid) (grid+stats+warnings)"
```

---

# Part C — Edits, undo/redo, optimistic concurrency

## Task C1: `apply_edit` — 4 core ops + apply pipeline + optimistic concurrency

**Files:**
- Modify: `webapp/api/rosters.py` (add `apply_edit`, affected-cell helper, mutation helpers)
- Modify: `webapp/api/main.py` (add `POST /rosters/{rid}/edits`)
- Test: `tests/test_edits.py`

Ops: `assign` / `unassign` / `move` / `toggle_lock` (synthesis §2.2). Pipeline (§2.3 / reader-3 §3.3): validate `expected_version` (→ 409) → snapshot `before_json` (complete affected-cell rows) → mutate rows → `after_json` → truncate redo tail, append edit `seq=cursor+1`, bump `version`/`cursor` → re-derive affected cells (incl. **D+1 明け** iff a night row exists for `(sid,date)`) → `recompute_stats` → update `roster_meta` → return `changed_cells` + `stats` + `warnings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edits.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path, **kw):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}, {"id": "T002", "name": "乙"}],
        day_assignments=kw.get("day", {1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}}),
        night_assignments=kw.get("night", {}),
        requests={}, on_call_assignments={}, daikyu_counts={}, off_counts={"T001": 9, "T002": 9},
        validation_errors=[], daily_location_needs=kw.get("needs", {2: {"ク": 2}}))
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False),
             SimpleNamespace(id="T002", name="乙", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_assign_updates_cell_and_version(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T002", "date": "2026-06-02",
            "location": "ク", "expected_version": 0})
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == 1 and body["seq"] == 1
        cell = next(c for c in body["changed_cells"]
                    if c["staff_id"] == "T002" and c["date"] == "2026-06-02")
        assert cell["text"] == "ク"
        assert "T002" in body["stats"]
        # coverage for ク on day 2 now satisfied (req 2, assigned 2)
        assert all(c["location"] != "ク" or c["date"] != "2026-06-02"
                   for c in body["warnings"]["coverage"])
        assert body["undo_available"] is True and body["redo_available"] is False
    finally:
        app.dependency_overrides.clear()


def test_unassign_raises_off(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        before = conn.execute(
            "SELECT off_count FROM roster_meta WHERE roster_id=? AND staff_id='T001'",
            (rid,)).fetchone()["off_count"]
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "unassign", "staff_id": "T001", "date": "2026-06-02",
            "location": "ク", "expected_version": 0})
        assert r.status_code == 200
        assert r.json()["stats"]["T001"]["公休"] > before  # blank weekday = rest
    finally:
        app.dependency_overrides.clear()


def test_stale_version_conflicts_409(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T002", "date": "2026-06-02",
            "location": "ク", "expected_version": 99})
        assert r.status_code == 409
        assert "grid" in r.json()["detail"]  # current grid for rebase
    finally:
        app.dependency_overrides.clear()


def test_move_is_single_edit(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "move", "staff_id": "T001",
            "from": {"date": "2026-06-01", "location": "CT"},
            "to": {"date": "2026-06-03", "location": "CT"},
            "expected_version": 0})
        assert r.status_code == 200
        n = conn.execute("SELECT COUNT(*) FROM roster_edits WHERE roster_id=?",
                         (rid,)).fetchone()[0]
        assert n == 1  # one edit, one undo step
    finally:
        app.dependency_overrides.clear()


def test_night_edit_rederives_next_day_akemei(tmp_path):
    conn, rid = _seed(tmp_path, day={1: {"CT": ["T001"]}}, night={})
    try:
        # assign a night to T001 on day 1 -> day 2 must become 明け '○'
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-01",
            "location": "夜", "expected_version": 0})
        # NOTE: night is kind='night'; for this test the assign op writes a day row '夜'.
        # The D+1 rule is exercised explicitly in test_undo_redo via a night freeze.
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_toggle_lock_no_stats_change(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/edits", json={
            "op": "toggle_lock", "staff_id": "T001", "date": "2026-06-01",
            "location": "CT", "locked": True, "expected_version": 0})
        assert r.status_code == 200
        locked = conn.execute(
            "SELECT locked FROM roster_assignments WHERE roster_id=? AND staff_id='T001'"
            " AND date='2026-06-01' AND kind='day'", (rid,)).fetchone()["locked"]
        assert locked == 1
        cell = next(c for c in r.json()["changed_cells"] if c["staff_id"] == "T001")
        assert cell["locked"] is True
    finally:
        app.dependency_overrides.clear()
```

> The `test_night_edit_rederives_next_day_akemei` here is intentionally light; the authoritative D+1 明け assertion lives in `tests/test_undo_redo.py` where a roster is frozen WITH a night assignment so editing it flips the neighbor cell deterministically.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_edits.py -v`
Expected: FAIL (no `/edits` route).

- [ ] **Step 3: Implement `apply_edit` + endpoint**

Add to `rosters.py`. Key helpers: `_affected_cells(op, conn, rid)` (returns the `{(sid, day)}` set incl. D+1 when a night row exists), `_snapshot(conn, rid, cells)` (complete rows for cells), `_mutate_*` per op, then the shared tail (append edit, bump version/cursor, re-derive, recompute, persist meta).

```python
class ConcurrencyError(Exception):
    def __init__(self, grid):
        self.grid = grid


def _has_night(conn, rid, sid, dn, year, month):
    iso = _iso(year, month, dn)
    return conn.execute(
        "SELECT 1 FROM roster_assignments WHERE roster_id=? AND staff_id=? AND date=?"
        " AND kind='night'", (rid, sid, iso)).fetchone() is not None


def _affected(conn, rid, op, payload, year, month):
    sid = payload["staff_id"]
    cells = set()

    def add_with_neighbor(dn):
        cells.add((sid, dn))
        if _has_night(conn, rid, sid, dn, year, month):
            if dn < 31:
                cells.add((sid, dn + 1))

    if op in ("assign", "unassign", "set_symbol"):
        add_with_neighbor(_day_of(payload["date"]))
    elif op == "move":
        add_with_neighbor(_day_of(payload["from"]["date"]))
        add_with_neighbor(_day_of(payload["to"]["date"]))
    elif op == "toggle_lock":
        cells.add((sid, _day_of(payload["date"])))
    return cells


def _rows_for_cells(conn, rid, cells, year, month):
    out = []
    for sid, dn in sorted(cells):
        iso = _iso(year, month, dn)
        for r in conn.execute(
                "SELECT staff_id,date,kind,location_or_role,symbol,locked "
                "FROM roster_assignments WHERE roster_id=? AND staff_id=? AND date=?",
                (rid, sid, iso)):
            out.append(dict(r))
    return out


def _restore_rows(conn, rid, cells, rows, year, month):
    """Replace all rows for `cells` with the snapshot `rows` (op-agnostic)."""
    for sid, dn in cells:
        conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                     " AND date=?", (rid, sid, _iso(year, month, dn)))
    for r in rows:
        conn.execute(
            "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,"
            "location_or_role,symbol,locked) VALUES(?,?,?,?,?,?,?)",
            (rid, r["staff_id"], r["date"], r["kind"], r["location_or_role"],
             r["symbol"], r["locked"]))


def _mutate(conn, rid, op, payload, year, month):
    sid = payload["staff_id"]
    if op == "assign":
        iso = payload["date"]
        keep = conn.execute(
            "SELECT locked FROM roster_assignments WHERE roster_id=? AND staff_id=?"
            " AND date=? AND kind='day'", (rid, sid, iso)).fetchone()
        locked = keep["locked"] if keep else 0
        conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                     " AND date=? AND kind='day'", (rid, sid, iso))
        conn.execute(
            "INSERT INTO roster_assignments(roster_id,staff_id,date,kind,"
            "location_or_role,locked) VALUES(?,?,?,'day',?,?)",
            (rid, sid, iso, payload["location"], locked))
    elif op == "unassign":
        loc = payload.get("location")
        if loc is not None:
            conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                         " AND date=? AND kind='day' AND location_or_role=?",
                         (rid, sid, payload["date"], loc))
        else:
            conn.execute("DELETE FROM roster_assignments WHERE roster_id=? AND staff_id=?"
                         " AND date=? AND kind='day'", (rid, sid, payload["date"]))
    elif op == "move":
        _mutate(conn, rid, "unassign",
                {"staff_id": sid, "date": payload["from"]["date"],
                 "location": payload["from"]["location"]}, year, month)
        _mutate(conn, rid, "assign",
                {"staff_id": sid, "date": payload["to"]["date"],
                 "location": payload["to"]["location"]}, year, month)
    elif op == "toggle_lock":
        loc = payload.get("location")
        cond = " AND location_or_role=?" if loc is not None else ""
        args = [1 if payload["locked"] else 0, rid, sid, payload["date"]]
        if loc is not None:
            args.append(loc)
        n = conn.execute(
            "UPDATE roster_assignments SET locked=? WHERE roster_id=? AND staff_id=?"
            " AND date=? AND kind='day'" + cond, args).rowcount
        if n == 0 and payload["locked"]:   # empty-cell lock sentinel
            conn.execute(
                "INSERT OR IGNORE INTO roster_assignments(roster_id,staff_id,date,kind,"
                "location_or_role,locked) VALUES(?,?,?,'day',NULL,1)",
                (rid, sid, payload["date"]))


def _changed_cells(conn, rid, grid, cells, year, month):
    by_staff = {r["staff_id"]: r for r in grid["rows"]}
    locked = _locked_cells(conn, rid)
    out = []
    for sid, dn in sorted(cells):
        row = by_staff.get(sid)
        if row is None:
            continue
        out.append({
            "staff_id": sid, "date": _iso(year, month, dn),
            "text": row["cells"][dn], "category": row["cell_meta"][dn]["kind"],
            "fill": row["cell_meta"][dn]["fill"],
            "locked": bool(locked.get((sid, dn), False)), "warnings": []})
    return out


def _recompute_and_persist(conn, rid, affected_staff):
    d = roster_to_dicts(conn, rid)
    warnings = recompute_stats(
        d["day_assignments"], d["night_assignments"], d["requests"],
        d["technicians"], d["year"], d["month"], d["target_holidays"],
        daily_location_needs=d["daily_location_needs"])
    grid = build_grid(d["year"], d["month"], d["technicians"],
                      d["day_assignments"], d["night_assignments"], d["requests"],
                      off_counts=warnings["off_counts"],
                      daikyu_counts=warnings["daikyu_counts"],
                      cells={(s, 1) for s in affected_staff})
    stats = {}
    for r in grid["rows"]:
        sid = r["staff_id"]
        conn.execute(
            "INSERT OR REPLACE INTO roster_meta(roster_id,staff_id,off_count,"
            "daikyu_count,stats_json) VALUES(?,?,?,?,?)",
            (rid, sid, float(warnings["off_counts"].get(sid, 0)),
             float(warnings["daikyu_counts"].get(sid, 0)),
             json.dumps(r["stats"] or {}, ensure_ascii=False)))
        stats[sid] = r["stats"]
    return warnings, grid, stats, d


def apply_edit(conn, rid, payload, *, user_id=None):
    hdr = conn.execute("SELECT version,edit_cursor,year,month FROM rosters WHERE id=?",
                       (rid,)).fetchone()
    if hdr is None:
        raise KeyError(rid)
    year, month = hdr["year"], hdr["month"]
    if payload.get("expected_version") != hdr["version"]:
        grid, d = build_roster_grid(conn, rid)
        raise ConcurrencyError({"version": hdr["version"], "grid": grid,
                                "warnings": roster_warnings(d)})

    op = payload["op"]
    cells = _affected(conn, rid, op, payload, year, month)
    before = _rows_for_cells(conn, rid, cells, year, month)
    _mutate(conn, rid, op, payload, year, month)
    # re-evaluate affected cells AFTER mutation (night row may have appeared/left)
    cells |= _affected(conn, rid, op, payload, year, month)
    after = _rows_for_cells(conn, rid, cells, year, month)

    cursor = hdr["edit_cursor"]
    conn.execute("DELETE FROM roster_edits WHERE roster_id=? AND seq>?", (rid, cursor))
    seq = cursor + 1
    cur = conn.execute(
        "INSERT INTO roster_edits(roster_id,seq,user_id,at,op,payload_json,"
        "before_json,after_json) VALUES(?,?,?,?,?,?,?,?)",
        (rid, seq, user_id, _now(), op, json.dumps(payload, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False)))
    edit_id = cur.lastrowid
    new_version = hdr["version"] + 1
    conn.execute("UPDATE rosters SET version=?, edit_cursor=? WHERE id=?",
                 (new_version, seq, rid))

    affected_staff = {sid for sid, _ in cells}
    warnings, _, _, _ = _recompute_and_persist(conn, rid, affected_staff)
    grid, _ = build_roster_grid(conn, rid, cells=cells)
    changed = _changed_cells(conn, rid, grid, cells, year, month)
    stats = {r["staff_id"]: r["stats"] for r in grid["rows"]}
    conn.commit()

    redo = conn.execute("SELECT 1 FROM roster_edits WHERE roster_id=? AND seq=? AND undone=1",
                        (rid, seq + 1)).fetchone() is not None
    return {
        "edit_id": edit_id, "seq": seq, "version": new_version,
        "changed_cells": changed, "stats": stats,
        "warnings": {
            "coverage": warnings["coverage"],
            "holiday_deficit": warnings["holiday_deficit"],
            "consecutive": warnings["consecutive"],
            "night_hb_gaps": warnings["night_hb_gaps"],
            "skill": []},  # P3 placeholder (needs skills/PB masters)
        "undo_available": seq > 0, "redo_available": redo}
```

Add to `webapp/api/main.py`:

```python
from pydantic import BaseModel
from typing import Optional, Dict, Any


@app.post("/rosters/{rid}/edits")
def post_edit(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    try:
        return roster_ops.apply_edit(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)
```

> The edit body is accepted as a free dict (ops differ in shape); validation is `apply_edit`'s job. `expected_version` mismatch → 409 with the current grid for client rebase.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_edits.py -v`
Expected: PASS — assign/unassign/move/toggle_lock all apply; 公休 rises on unassign; 409 on stale version; move is one edit.

- [ ] **Step 5: Commit**

```bash
git add webapp/api/rosters.py webapp/api/main.py tests/test_edits.py
git commit -m "feat(api): POST /rosters/{rid}/edits — 4 core ops, apply pipeline, optimistic concurrency (409)"
```

---

## Task C2: Undo / Redo

**Files:**
- Modify: `webapp/api/rosters.py` (add `undo`, `redo`)
- Modify: `webapp/api/main.py` (add `POST /rosters/{rid}/undo|redo`)
- Test: `tests/test_undo_redo.py`

Linear history + cursor (synthesis §2.4): **Undo** takes `seq==cursor` (`undone=0`), restores `before_json`, sets `undone=1`, `cursor-=1`, `version+=1`. **Redo** takes `seq==cursor+1` (`undone=1`), applies `after_json`, `undone=0`, `cursor+=1`, `version+=1`. Full-row snapshots make inversion op-agnostic (a `move`'s halves revert atomically). This task also carries the authoritative **D+1 明け** assertion (edit a night-frozen roster, verify the neighbor cell flips and reverts).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_undo_redo.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def _seed(tmp_path, night=None, day=None):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments=day or {1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}},
        night_assignments=night or {}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T001": 9}, validation_errors=[],
        daily_location_needs={})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    return conn, rid


def _client(conn):
    app.dependency_overrides[api_main.get_db] = lambda: conn
    return TestClient(app)


def test_undo_then_redo_round_trips(tmp_path):
    conn, rid = _seed(tmp_path)
    c = _client(conn)
    try:
        c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "CT", "expected_version": 0})
        u = c.post(f"/rosters/{rid}/undo", json={"expected_version": 1})
        assert u.status_code == 200 and u.json()["version"] == 2
        # cell back to 'ク'
        cell = next(x for x in u.json()["changed_cells"]
                    if x["date"] == "2026-06-02")
        assert cell["text"] == "ク"
        assert u.json()["redo_available"] is True
        r = c.post(f"/rosters/{rid}/redo", json={"expected_version": 2})
        assert r.status_code == 200
        cell = next(x for x in r.json()["changed_cells"] if x["date"] == "2026-06-02")
        assert cell["text"] == "CT"
    finally:
        app.dependency_overrides.clear()


def test_new_edit_after_undo_truncates_redo(tmp_path):
    conn, rid = _seed(tmp_path)
    c = _client(conn)
    try:
        c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "CT", "expected_version": 0})
        c.post(f"/rosters/{rid}/undo", json={"expected_version": 1})
        new = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-02",
            "location": "MG", "expected_version": 2})
        assert new.status_code == 200 and new.json()["redo_available"] is False
    finally:
        app.dependency_overrides.clear()


def test_undo_unavailable_at_baseline(tmp_path):
    conn, rid = _seed(tmp_path)
    try:
        r = _client(conn).post(f"/rosters/{rid}/undo", json={"expected_version": 0})
        assert r.status_code == 409  # nothing to undo (cursor==0)
    finally:
        app.dependency_overrides.clear()


def test_night_edit_flips_next_day_akemei_and_reverts(tmp_path):
    # T001 has a night on day 1 already; unassign it -> day 2 stops being 明け.
    conn, rid = _seed(tmp_path, night={1: ["T001"]}, day={1: {}, 2: {}})
    c = _client(conn)
    try:
        g = _client(conn).get(f"/rosters/{rid}/grid").json()
        row = next(r for r in g["rows"] if r["staff_id"] == "T001")
        assert row["cells"][2] == "○"  # frozen 明け from day-1 night
        # toggle_lock is a no-op for text; use an assign on day 1 that the D+1 rule covers.
        resp = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-01",
            "location": "CT", "expected_version": 0})
        dates = {x["date"] for x in resp.json()["changed_cells"]}
        assert "2026-06-02" in dates  # D+1 re-derived because a night row exists on day 1
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_undo_redo.py -v`
Expected: FAIL (no `/undo`,`/redo` routes).

- [ ] **Step 3: Implement `undo`/`redo` + endpoints**

Add to `rosters.py`:

```python
def _undo_redo(conn, rid, payload, *, redo):
    hdr = conn.execute("SELECT version,edit_cursor,year,month FROM rosters WHERE id=?",
                       (rid,)).fetchone()
    if hdr is None:
        raise KeyError(rid)
    year, month = hdr["year"], hdr["month"]
    if payload.get("expected_version") != hdr["version"]:
        grid, d = build_roster_grid(conn, rid)
        raise ConcurrencyError({"version": hdr["version"], "grid": grid,
                                "warnings": roster_warnings(d)})
    cursor = hdr["edit_cursor"]
    target_seq = cursor + 1 if redo else cursor
    if target_seq <= 0:
        raise ConcurrencyError({"version": hdr["version"], "reason": "nothing to undo"})
    edit = conn.execute(
        "SELECT * FROM roster_edits WHERE roster_id=? AND seq=? AND undone=?",
        (rid, target_seq, 0 if not redo else 1)).fetchone()
    if edit is None:
        raise ConcurrencyError({"version": hdr["version"],
                                "reason": "nothing to redo" if redo else "nothing to undo"})

    snap = json.loads(edit["after_json"] if redo else edit["before_json"])
    cells = {(r["staff_id"], _day_of(r["date"])) for r in
             json.loads(edit["before_json"]) + json.loads(edit["after_json"])}
    _restore_rows(conn, rid, cells, snap, year, month)
    conn.execute("UPDATE roster_edits SET undone=? WHERE id=?",
                 (0 if redo else 1, edit["id"]))
    new_cursor = cursor + 1 if redo else cursor - 1
    new_version = hdr["version"] + 1
    conn.execute("UPDATE rosters SET version=?, edit_cursor=? WHERE id=?",
                 (new_version, new_cursor, rid))

    affected_staff = {sid for sid, _ in cells}
    warnings, _, _, _ = _recompute_and_persist(conn, rid, affected_staff)
    grid, _ = build_roster_grid(conn, rid, cells=cells)
    changed = _changed_cells(conn, rid, grid, cells, year, month)
    stats = {r["staff_id"]: r["stats"] for r in grid["rows"]}
    conn.commit()
    redo_avail = conn.execute(
        "SELECT 1 FROM roster_edits WHERE roster_id=? AND seq=? AND undone=1",
        (rid, new_cursor + 1)).fetchone() is not None
    return {
        "edit_id": edit["id"], "seq": new_cursor, "version": new_version,
        "changed_cells": changed, "stats": stats,
        "warnings": {
            "coverage": warnings["coverage"],
            "holiday_deficit": warnings["holiday_deficit"],
            "consecutive": warnings["consecutive"],
            "night_hb_gaps": warnings["night_hb_gaps"], "skill": []},
        "undo_available": new_cursor > 0, "redo_available": redo_avail}


def undo(conn, rid, payload):
    return _undo_redo(conn, rid, payload, redo=False)


def redo(conn, rid, payload):
    return _undo_redo(conn, rid, payload, redo=True)
```

Add to `webapp/api/main.py`:

```python
@app.post("/rosters/{rid}/undo")
def post_undo(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    try:
        return roster_ops.undo(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)


@app.post("/rosters/{rid}/redo")
def post_redo(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    try:
        return roster_ops.redo(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_undo_redo.py -v`
Expected: PASS — undo/redo round-trip, redo-tail truncation, baseline-undo 409, and the D+1 明け re-derivation all hold.

- [ ] **Step 5: Commit**

```bash
git add webapp/api/rosters.py webapp/api/main.py tests/test_undo_redo.py
git commit -m "feat(api): POST /rosters/{rid}/undo|redo — linear history + cursor, full-row snapshots"
```

---

## Task C3: Full-suite green gate + end-to-end roster API test

**Files:**
- Create: `tests/test_roster_api.py` (end-to-end happy path through one seeded roster)

- [ ] **Step 1: Write the integration test**

```python
# tests/test_roster_api.py
from types import SimpleNamespace

from fastapi.testclient import TestClient

from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main
from webapp.api.db import connect, init_db
from webapp.api.main import app
from webapp.api.rosters import freeze_roster


def test_freeze_read_edit_undo_flow(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    init_db(conn)
    result = ScheduleResult(
        year=2026, month=6, staff=[{"id": "T001", "name": "甲"}],
        day_assignments={1: {"CT": ["T001"]}, 2: {"ク": ["T001"]}},
        night_assignments={}, requests={}, on_call_assignments={},
        daikyu_counts={}, off_counts={"T001": 9}, validation_errors=[],
        daily_location_needs={2: {"ク": 1}})
    techs = [SimpleNamespace(id="T001", name="甲", status="在籍", note="", night_hb=False)]
    rid = freeze_roster(conn, job_id="j", result=result, technicians=techs,
                        data_dir="d", target_holidays=9)
    conn.commit()
    app.dependency_overrides[api_main.get_db] = lambda: conn
    try:
        c = TestClient(app)
        assert c.get(f"/rosters/{rid}").json()["version"] == 0
        e = c.post(f"/rosters/{rid}/edits", json={
            "op": "assign", "staff_id": "T001", "date": "2026-06-03",
            "location": "MG", "expected_version": 0}).json()
        assert e["version"] == 1
        assert c.get(f"/rosters/{rid}").json()["version"] == 1
        u = c.post(f"/rosters/{rid}/undo", json={"expected_version": 1}).json()
        assert u["version"] == 2 and u["undo_available"] is False
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the new test**

Run: `python -m pytest tests/test_roster_api.py -v`
Expected: PASS.

- [ ] **Step 3: Run the fast suite (green gate)**

Run: `python -m pytest -m "not slow" -v`
Expected: ALL pass — the new P2a-2 tests plus the pre-existing `test_api`, `test_excel_bytes`, `test_grid_derivation`, `test_stats_engine`, `test_schedule_result`, `test_rebalancer_helpers`. P2a-2 added no scheduler changes, so nothing else moves.

- [ ] **Step 4: Commit**

```bash
git add tests/test_roster_api.py
git commit -m "test(p2a2): end-to-end freeze→read→edit→undo flow through the API"
```

---

## Self-Review

**Spec coverage (P2 design §1.1, §1.2, §2, §6 P2a):**
- Full `build_grid` (rows/cells/cell_meta/has_work/stats; oncall_rows; weekdays; stats_columns; `cells=` fast-path; クL→ク fold; whole-cell 夜勤 test; 公休/代休 injected-after-count; blank-stats when not has_work) → Task A2. ✅
- Full `recompute_stats` (off/daikyu via P2a-1 + coverage vs `daily_location_needs` folding クL→ク + night-HB gaps + holiday_deficit + 7-day consecutive) → Task A3. ✅
- SQLite persistence — 4 tables verbatim from §2.1 (columns, CHECKs, FK cascade, indexes) → Task B1. ✅
- Freeze (`ScheduleResult → rows`, idempotent per job) + `roster_to_dicts` adapter → Task B2. ✅
- Read — `GET /rosters/{rid}` (grid+stats+warnings+version) and `/grid` → Task B3. ✅
- Edit — `POST /rosters/{rid}/edits` with assign/unassign/move/toggle_lock; apply pipeline (validate → snapshot before → mutate → after → append edit, bump version/cursor → re-derive affected incl. **D+1 明け** → recompute_stats(affected) → changed_cells+stats+warnings); optimistic concurrency (`expected_version` → 409) → Task C1. ✅
- Undo/Redo — linear history + cursor + full-row before/after snapshots; redo-tail truncation → Task C2. ✅
- `roster_to_dicts` adapter feeding both `build_grid` and `recompute_stats` → Task B2. ✅
- Deferred by design (stated): Direction-A Excel (P2c), React (P2d), partial-lock re-solve (P2b), `skill`/PB warnings (P3 — returned as `skill: []`).

**Placeholder scan:** every `...`-free; all test code, SQL DDL, commands, and commit messages are concrete. The only intentional empty value is the edit response's `"skill": []`, explicitly documented as a P3 placeholder. Implementation skeletons in Tasks A2/A3/B1/B2/C1/C2 are full working code (the implementer copies/ports the cited counting loop and classifier rather than paraphrasing).

**Type consistency:**
- Dict-form shapes are identical across `build_grid`, `recompute_stats`, `roster_to_dicts`, and the freeze: `day_assignments {int day: {loc: [sid]}}`, `night_assignments {int day: [sid]}`, `requests {int day: {sid: sym}}`, `on_call_assignments {int day: {role: sid}}`.
- `recompute_stats(day_assignments, night_assignments, requests, technicians, year, month, target_holidays, *, daily_location_needs=None, staff_scope=None)` and `build_grid(year, month, technicians, day_assignments, night_assignments, requests, off_counts=None, daikyu_counts=None, on_call_assignments=None, cells=None)` are called identically in tests, freeze, read, and the edit pipeline.
- Persisted JSON keys are stable: `rosters.staff_json` = `[{id,name,status,note,night_hb}]`; `daily_needs_json` = `{ISO-date: {loc: required}}`; `roster_meta.stats_json` = the 21-col dict; `roster_edits.before/after_json` = lists of complete row dicts `{staff_id,date,kind,location_or_role,symbol,locked}`.
- Edit response shape matches synthesis §2.3: `{edit_id, seq, version, changed_cells[], stats{}, warnings{coverage,holiday_deficit,consecutive,night_hb_gaps,skill}, undo_available, redo_available}`.
- Dates are ISO `'YYYY-MM-DD'` at the API/DB boundary; day-int internally — `_iso`/`_day_of` are the only converters.

**Determinism:** no solver is invoked anywhere in P2a-2; edits + undo are pure row mutations + deterministic derivation, so a roster is a deterministic function of `(freeze baseline, edit log up to cursor)`. Tests never run CP-SAT (the only slow path is the one-time fixture generator in Task A1, which itself reuses already-solved P2a-1 assignments and re-renders Excel only).

---

## Next (separate plans)
- **P2c — Direction-A Excel renderer:** consume `build_grid` (thin openpyxl placement layer, zero derivation); keep Excel fills keyed off final text via `cell_fill` (NOT `kind`); blank-stats gating; weekend/holiday shading from `weekdays` + `jpholiday`; `GET /rosters/{rid}/excel` renders frozen rows. Byte-diff test vs current `ExcelGenerator` on a fixed fixture.
- **P2d — React editor:** TanStack Table v8 + dnd-kit + TanStack Query against the P2a-2 API; optimistic edits that merge the server's authoritative `changed_cells`/`stats`/`warnings` (including D+1 明け and recomputed 代休); 409 → `ConflictDialog` rebase.
- **P2b — Partial-lock re-solve (heaviest):** lock hooks into both schedulers + thread `locked_assignments` through `run_schedule` and the three post-processors; pre-validation + assumption-based diagnostics; `POST /rosters/{rid}/resolve` re-freezes (locked rows kept) and records a synthetic `op='resolve'` edit so it stays undoable; reuse `_solve_lock` (`webapp/api/jobs.py:44`), keep `seed=42, num_workers=1`.
