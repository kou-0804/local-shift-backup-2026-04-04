# Web App P2c — Direction-A Excel Redesign (render from build_grid) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the visual redesign of the shift-table Excel (spec §6.5, "方向A"). Two coordinated moves: (a) **refactor the existing `ExcelGenerator` so it renders FROM `build_grid(...)`** (the pure dict delivered by P2a-2) instead of its own inline derivation/counting — proven byte-identical to today's `.xlsx` by a captured golden dump; and (b) **add a brand-new Direction-A renderer** (`excel_directiona.py`) that consumes the same `build_grid` dict and applies the §6.5 layout/colours (shift-type colour-coding, day-tracking title, 2-row weekend/holiday header, freeze panes, 凡例 + 集計 sheets, A3-landscape print setup). The `GET /rosters/{rid}/excel` endpoint serves Direction-A from the frozen roster; the legacy renderer stays importable purely as the parity reference. Validation/warning sheet is regenerated from **live `recompute_stats`** rather than frozen `validation_errors`.

**Architecture:** `build_grid(...)` (P2a-2) is the single source of derived data — cell texts, per-cell `cell_meta{kind,fill}`, per-row `stats`, `weekdays`, `oncall_rows`. P2c is a **thin openpyxl placement layer** over that dict and does **ZERO derivation**. Two renderers consume it:
- **Legacy `ExcelGenerator`** — keeps today's exact look. Cell fills MUST stay keyed off the final **text** via `cell_meta[day]["fill"]` (== `grid_derivation.cell_fill(text)`), **NOT** off `kind`. This is the parity reference.
- **New Direction-A renderer** — free to key colours off `cell_meta[day]["kind"]` (夜/明け/公休/希望休/…), because it is a *separate* output and is validated by visual-structure assertions, not byte-identity.

This split cleanly resolves the apparent tension in the spec: "fills keyed off text, not kind" is a **legacy-parity** invariant; "shift-type colour-coding from kind" is a **Direction-A** feature.

**Tech Stack:** Python 3.13, pytest, openpyxl, jpholiday (already a runtime dep, used by `main.py`). FastAPI + Starlette `TestClient` for the endpoint test. No new dependencies.

**Scope note:** P2c is the Excel render layer + its endpoint wiring only. It assumes P2a-1 (shipped: `grid_derivation.derive_cell_text`/`cell_fill`, `ExcelGenerator` already delegates to them byte-identically) and P2a-2 (in flight: `grid_derivation.build_grid(...)`, `stats_engine.recompute_stats(...)`, the roster store + `GET /rosters/{rid}/excel` route) are present. **Treat `build_grid` and `recompute_stats` as existing.** Determinism is mandatory: same frozen roster → byte-identical Direction-A bytes.

**Provenance (grounded against the current tree):**
- `shift_scheduler/src/excel_generator.py` (312 lines). Main sheet title `self.ws.title = f"{month}月勤務表"` (`:48`); `generate_bytes() -> bytes` (`:65`); title merge hardcoded `A1:AH1` — the 34-col bug §6.5 calls out (`:75`); day column map `col_num = day + 2` (`:81`); 21 `stats_columns` declared 3× (`:100,144,316` in the pre-P2a1 layout); validation sheet `'検証レポート(自動診断)'` title `f"{year}年{month}月 勤務表 検証レポート"` merged `A1:E1` (`:282-286`).
- `shift_scheduler/src/grid_derivation.py` (P2a-1): `derive_cell_text(...)`, `cell_fill(text)->hex|None`. **P2a-2 adds `build_grid(...)` here.** Return shape (from the P2 internals map):
  ```python
  {year, month, days_in_month,
   weekdays:   {day:int -> '月'..'日'},
   stats_columns: [21 labels],
   rows: [{staff_id, staff_num, name,
           cells:     {day:int -> text},
           cell_meta: {day:int -> {"kind": str, "fill": hex|None}},
           has_work:  bool,
           stats:     {label->int|float} | None}],       # None when not has_work
   oncall_rows: [{"label": "第1拘束"|"第2拘束", "cells": {day:int -> name}}]}
  ```
  `kind ∈ {"night","akemei","special_off","off","request","work","empty"}`. `fill ∈ {"FFFF00"(夜),"FFC0CB"(明け○),"FFCDD2"(★☆◆),"D3D3D3"(休),None}`.
- `stats_engine.recompute_stats(...)` (P2a-2): pure, solver-free; returns `{off_counts, daikyu_counts, understaffing, night_hb_gaps, consecutive_work_violations}`. P2c formats these into warning strings for the validation sheet.
- `webapp/api/main.py`: existing `GET /jobs/{job_id}/excel` (`:53`) shows the Response/Content-Disposition pattern (RFC 5987 UTF-8 filename) to mirror for `/rosters/{rid}/excel`.
- Tests live under `tests/`, golden fixtures under `tests/golden/`; `pytest.ini` ignores `archive/` and registers the `slow` marker. Run with `python -m pytest`.

---

## File Structure

- Create `tests/golden/xlsx_dump.py` — shared, importable normalize-a-workbook helper (`dump_workbook(xlsx_bytes) -> dict`, `fill_hex(cell)`). Used by the fixture generator AND the parity test.
- Create `tests/golden/gen_excel_parity_fixture.py` — one-time generator: runs the real solver once, builds the **current** `ExcelGenerator`, and dumps `(constructor inputs serialized) + (normalized output dump)` to JSON. Captured from PRE-refactor code.
- Create (generated, committed) `tests/golden/2026-06_excel_parity.json` — the parity golden.
- Create `tests/test_excel_parity.py` — rebuilds `ExcelGenerator` offline from the fixture inputs and asserts its normalized dump == the golden. Guards the refactor.
- Modify `shift_scheduler/src/excel_generator.py` — replace the inline per-row derivation/counting with a single `build_grid(...)` call; place `cells`, fills (from `cell_meta.fill`), and `stats` from the dict. Header/border/width/title formatting unchanged.
- Create `shift_scheduler/src/excel_directiona.py` — `render_directiona(grid, *, warnings=None) -> bytes` plus the Direction-A palette + `_style_for(kind)` + layout helpers.
- Create `tests/test_excel_directiona.py` — visual-structure assertions over a small synthetic `build_grid` dict (no solver): sheetnames, `ws.freeze_panes`, title merge width, weekend/holiday fills, kind→colour, legend + summary sheets, print setup, live-warning sheet.
- Modify `webapp/api/main.py` — wire `GET /rosters/{rid}/excel` to: load frozen roster → `build_grid(...)` → `recompute_stats(...)` → `render_directiona(...)` → `Response(xlsx)`. Keep `ExcelGenerator` importable for the parity test only.
- Modify `tests/test_api.py` (or new `tests/test_api_excel.py`) — endpoint returns a valid Direction-A `.xlsx` (correct media-type, sheetnames, freeze panes) for a seeded roster.

All commands assume cwd is the repo root `"/Users/kohei/Desktop/local-shift ver1"` with the venv active (`source .venv/bin/activate`). Commit messages below are the literal subject lines; append the repo footer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` per house convention. Do not commit until a task's tests are green.

---

## Task 1: Shared workbook-normalizer + capture the pre-refactor parity golden

Capture the EXACT current `.xlsx` shape BEFORE touching `ExcelGenerator`, mirroring how P2a-1 captured `2026-06_p2a1.json`. "Byte-identity" here means **equality of a normalized cell+fill+stats+structure dump** (openpyxl does not guarantee stable zip bytes), which is the meaningful invariant.

**Files:**
- Create: `tests/golden/xlsx_dump.py`
- Create: `tests/golden/gen_excel_parity_fixture.py`
- Create (generated): `tests/golden/2026-06_excel_parity.json`

- [ ] **Step 1: Write the normalizer helper.**

```python
# tests/golden/xlsx_dump.py
"""Normalize an .xlsx to a JSON-able dict so two workbooks can be compared for
'byte-identity' independent of openpyxl's zip ordering. Shared by the parity
fixture generator and the parity test."""
from io import BytesIO
import openpyxl


def fill_hex(cell):
    """Solid-fill foreground colour as a 6-char hex, or None when unfilled.
    Normalizes openpyxl's optional 8-char ARGB ('00FFFF00') down to 'FFFF00'."""
    fill = cell.fill
    if fill is None or fill.patternType is None:
        return None
    rgb = getattr(fill.fgColor, "rgb", None)
    if not isinstance(rgb, str):
        return None
    return rgb[-6:].upper()


def dump_workbook(xlsx_bytes) -> dict:
    wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
    sheets = {}
    for ws in wb.worksheets:
        cells = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is None and fill_hex(c) is None:
                    continue
                cells[c.coordinate] = [c.value, fill_hex(c)]
        sheets[ws.title] = {
            "cells": cells,
            "merged": sorted(str(r) for r in ws.merged_cells.ranges),
            "freeze_panes": ws.freeze_panes,
            "max_row": ws.max_row,
            "max_col": ws.max_column,
        }
    return {"sheetnames": wb.sheetnames, "sheets": sheets}
```

- [ ] **Step 2: Write the one-time fixture generator** (runs the real solver once; not collected by pytest — it lives in `tests/golden/` and is invoked by hand, exactly like `gen_p2a1_fixture.py`).

```python
# tests/golden/gen_excel_parity_fixture.py
"""One-time generator. Runs the real solver for 2026-06, builds the CURRENT
ExcelGenerator, and captures (constructor inputs serialized) + (normalized output
dump). The parity test rebuilds ExcelGenerator OFFLINE from these inputs, so the
test stays fast/deterministic and proves the build_grid refactor is byte-safe.
Re-run only if the scheduler intentionally changes.
    Usage: python tests/golden/gen_excel_parity_fixture.py"""
import json
from main import run_schedule
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.excel_generator import ExcelGenerator
from tests.golden.xlsx_dump import dump_workbook

YEAR, MONTH, DATA_DIR = 2026, 6, "shift_scheduler/data"


def main():
    result = run_schedule(YEAR, MONTH, data_dir=DATA_DIR)
    technicians = DataLoader(data_dir=DATA_DIR).load_all(f"{YEAR}-{MONTH:02d}")[0]

    gen = ExcelGenerator(
        year=YEAR, month=MONTH, technicians=technicians,
        night_assignments=result.night_assignments,
        day_assignments=result.day_assignments,
        requests=result.requests,
        on_call_assignments=result.on_call_assignments,
        daikyu_counts=result.daikyu_counts,
        off_counts=result.off_counts,
        validation_errors=result.validation_errors,
    )
    dump = dump_workbook(gen.generate_bytes())

    # Serialize ONLY what ExcelGenerator reads off a Staff: id/name/status/note.
    techs = [{"id": t.id, "name": t.name, "status": t.status, "note": t.note}
             for t in technicians]
    fixture = {
        "year": YEAR, "month": MONTH,
        "technicians": techs,
        "day_assignments": result.day_assignments,
        "night_assignments": result.night_assignments,
        "requests": result.requests,
        "on_call_assignments": result.on_call_assignments,
        "daikyu_counts": result.daikyu_counts,
        "off_counts": result.off_counts,
        "validation_errors": result.validation_errors,
        "expected_dump": dump,
    }
    with open("tests/golden/2026-06_excel_parity.json", "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1)
    print("wrote tests/golden/2026-06_excel_parity.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate and inspect the fixture.**

```bash
source .venv/bin/activate
python tests/golden/gen_excel_parity_fixture.py
python -c "import json; d=json.load(open('tests/golden/2026-06_excel_parity.json')); print(d['expected_dump']['sheetnames']); print(len(d['technicians']),'techs')"
```

Expect sheetnames `['6月勤務表', '検証レポート(自動診断)']`.

- [ ] **Step 4: Commit.**

```bash
git add tests/golden/xlsx_dump.py tests/golden/gen_excel_parity_fixture.py tests/golden/2026-06_excel_parity.json
git commit  # subject: test(excel): capture pre-refactor parity golden + workbook normalizer
```

---

## Task 2: Characterization test — current ExcelGenerator == golden (the refactor guard)

Write the test that rebuilds `ExcelGenerator` OFFLINE from the fixture inputs and asserts its normalized dump equals the captured golden. It is GREEN against the current code; it must STAY green through Task 3. (This is the standard "characterize, then refactor under a green test" pattern.)

**Files:** Create `tests/test_excel_parity.py`

- [ ] **Step 1: Write the test.**

```python
# tests/test_excel_parity.py
import json
from collections import namedtuple
from shift_scheduler.src.excel_generator import ExcelGenerator
from tests.golden.xlsx_dump import dump_workbook

with open("tests/golden/2026-06_excel_parity.json", encoding="utf-8") as f:
    FIX = json.load(f)

# ExcelGenerator only reads .id/.name/.status/.note off each Staff -> a stub suffices.
StaffStub = namedtuple("StaffStub", "id name status note")
TECHS = [StaffStub(t["id"], t["name"], t["status"], t["note"]) for t in FIX["technicians"]]

# JSON keys are strings; ExcelGenerator/build_grid expect int day keys.
def _int_days(d):
    return {int(k): v for k, v in d.items()}


def _build():
    return ExcelGenerator(
        year=FIX["year"], month=FIX["month"], technicians=TECHS,
        night_assignments=_int_days(FIX["night_assignments"]),
        day_assignments=_int_days(FIX["day_assignments"]),
        requests=_int_days(FIX["requests"]),
        on_call_assignments=_int_days(FIX["on_call_assignments"]),
        daikyu_counts=FIX["daikyu_counts"],
        off_counts=FIX["off_counts"],
        validation_errors=FIX["validation_errors"],
    )


def test_excelgenerator_output_matches_golden_dump():
    got = dump_workbook(_build().generate_bytes())
    assert got == FIX["expected_dump"]
```

- [ ] **Step 2: Confirm GREEN against current code.**

```bash
python -m pytest tests/test_excel_parity.py -q
```

If RED here, the fixture serialization is lossy (e.g. float `off_counts`, `None` request entries, or string-vs-int day keys) — fix `_int_days`/stub fields until green BEFORE refactoring. Do not proceed otherwise.

- [ ] **Step 3: Commit.**

```bash
git add tests/test_excel_parity.py
git commit  # subject: test(excel): characterize ExcelGenerator output against parity golden
```

---

## Task 3: Refactor ExcelGenerator to render FROM build_grid (parity-preserving)

Replace the inline `_get_assignment_text` loop + the 21-column counting loop with a single `build_grid(...)` call, then place values from the returned dict. Header/border/width/title/validation formatting is untouched. **Fills come from `cell_meta[day]["fill"]`, never from `kind`** — this is what keeps the dump byte-identical.

**Files:** Modify `shift_scheduler/src/excel_generator.py`

- [ ] **Step 1: Build the grid once in `__init__` (or at the top of `generate_bytes`).**

```python
from shift_scheduler.src import grid_derivation

self.grid = grid_derivation.build_grid(
    year=year, month=month, technicians=technicians,
    day_assignments=day_assignments, night_assignments=night_assignments,
    requests=requests, off_counts=off_counts, daikyu_counts=daikyu_counts,
    on_call_assignments=on_call_assignments,
)
self.days_in_month = self.grid["days_in_month"]
self.stats_columns = self.grid["stats_columns"]
```

- [ ] **Step 2: Rewrite the row-fill loop to consume `self.grid["rows"]`.** For each row, for `day, text in row["cells"].items()`: write `text` at `_day_to_column(day)`; if `row["cell_meta"][day]["fill"]` is not None apply `PatternFill(start_color=fill, end_color=fill, fill_type='solid')`. When `row["has_work"]` and `row["stats"] is not None`, write `row["stats"][label]` into each stats column; else leave the stats block blank (preserves the existing `row_has_work` gate). Use `row["staff_num"]` for the 勤務表番号 column and `row["name"]` for 技師名. Delete the now-dead `_get_assignment_text`, `_get_cell_fill`, and the inline counting code (or have them raise to catch stragglers).

- [ ] **Step 3: Render on-call rows from `self.grid["oncall_rows"]`** (already name-cleaned by `build_grid`) — write `r["cells"][day]` per day, no stats. Keep the existing label styling.

- [ ] **Step 4: Confirm the parity test is STILL GREEN** (no diff in the dump).

```bash
python -m pytest tests/test_excel_parity.py tests/test_excel_bytes.py -q
```

Both must pass. If the dump diffs, the most likely culprits are: fill applied off `kind` instead of `fill`; `公休/代休` not overwritten from counts (must come from `stats`, which `build_grid` already injects post-parse); or a stats-block written for a `has_work=False` row. Fix until identical.

- [ ] **Step 5: Run the wider suite** to confirm nothing else regressed.

```bash
python -m pytest -q
```

- [ ] **Step 6: Commit.**

```bash
git add shift_scheduler/src/excel_generator.py
git commit  # subject: refactor(excel): render ExcelGenerator from build_grid (parity-preserving)
```

---

## Task 4: Direction-A skeleton — day-tracking title + 2-row weekend/holiday header

Begin the new renderer. TDD: write the structural assertions first (RED), then implement until green. Tests run over a small synthetic `build_grid` dict — no solver, fast and deterministic.

**Files:** Create `shift_scheduler/src/excel_directiona.py`, `tests/test_excel_directiona.py`

- [ ] **Step 1: Write the synthetic grid + first failing test.**

```python
# tests/test_excel_directiona.py
from io import BytesIO
import openpyxl
from openpyxl.utils import get_column_letter, range_boundaries
from shift_scheduler.src.excel_directiona import render_directiona

STATS = ['夜勤','病院MR','CLMR','病CT','CT','ア','心','ク','ポ','精',
         'MG','DR','HB','OP','入','病L','超遅','ク遅','M遅','公休','代休']


def _sample_grid():
    # 2026-06: day 6 = Sat(土), day 7 = Sun(日), day 14 = Sun. Hand-built to exercise
    # every kind without invoking the solver.
    weekdays = {1:'月',2:'火',3:'水',4:'木',5:'金',6:'土',7:'日'}
    def meta(kind, fill=None): return {"kind": kind, "fill": fill}
    row = {
        "staff_id": "T001", "staff_num": 1, "name": "佐藤(海)",
        "cells":     {1:"CT", 2:"病CT夜", 3:"○",  4:"休", 5:"☆", 6:"", 7:"希望休"},
        "cell_meta": {1:meta("work"), 2:meta("night","FFFF00"), 3:meta("akemei","FFC0CB"),
                      4:meta("off","D3D3D3"), 5:meta("special_off","FFCDD2"),
                      6:meta("empty"), 7:meta("request")},
        "has_work": True,
        "stats": {k: 0 for k in STATS} | {"夜勤":1, "CT":1, "病CT":1, "公休":8},
    }
    return {
        "year": 2026, "month": 6, "days_in_month": 7,
        "weekdays": weekdays, "stats_columns": STATS,
        "rows": [row],
        "oncall_rows": [{"label":"第1拘束","cells":{d:("佐藤海" if d==1 else "") for d in range(1,8)}}],
    }


def _load():
    return openpyxl.load_workbook(BytesIO(render_directiona(_sample_grid())))


def test_main_sheet_present_and_titled():
    wb = _load()
    assert wb.sheetnames[0].startswith("勤務")        # main grid sheet first


def test_title_merge_width_tracks_days_plus_offset():
    ws = _load().worksheets[0]
    # offset = 2 name/number cols + len(stats); width must equal days + offset (NOT 34).
    days, offset = 7, 2 + len(STATS)
    title_ranges = [r for r in ws.merged_cells.ranges if str(r).startswith("A1")]
    assert len(title_ranges) == 1
    min_c, _, max_c, _ = range_boundaries(str(title_ranges[0]))
    assert (max_c - min_c + 1) == days + offset


def test_two_row_header_dates_then_weekdays():
    ws = _load().worksheets[0]
    # row2 = dates 1..7 starting col C; row3 = weekday chars.
    assert [ws.cell(row=2, column=2 + d).value for d in range(1, 8)] == [1,2,3,4,5,6,7]
    assert [ws.cell(row=3, column=2 + d).value for d in range(1, 8)] == \
           ['月','火','水','木','金','土','日']


def test_weekend_and_holiday_columns_are_shaded():
    from tests.golden.xlsx_dump import fill_hex
    ws = _load().worksheets[0]
    sat = ws.cell(row=2, column=2 + 6)   # day 6 = 土
    sun = ws.cell(row=2, column=2 + 7)   # day 7 = 日
    assert fill_hex(sat) == "DDEBF7"     # 薄青
    assert fill_hex(sun) == "FCE4D6"     # 薄赤
```

- [ ] **Step 2: Implement the skeleton.**

```python
# shift_scheduler/src/excel_directiona.py
"""Direction-A Excel renderer (spec §6.5). Thin openpyxl placement layer over the
build_grid dict: ZERO derivation. Distinct from the legacy ExcelGenerator — colours
key off cell_meta['kind'] and the layout is redesigned. Deterministic."""
from io import BytesIO
from datetime import date
import jpholiday
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# Direction-A palette (intentionally different from legacy value-driven fills)
C_NIGHT   = "1F3864"   # 夜勤  濃紺 (white font)
C_AKEMEI  = "D9D9D9"   # 明け  薄グレー
C_OFF     = "E2EFDA"   # 公休  薄緑 (off / special_off)
C_SAT     = "DDEBF7"   # 土    薄青
C_SUNHOL  = "FCE4D6"   # 日/祝 薄赤
C_HEADER  = "4472C4"   # ヘッダ

_NAME_COLS = 2         # A=勤務表番号, B=技師名
_FIRST_DATA_ROW = 4    # row1 title, row2 dates, row3 weekdays
_DUTY_BORDER = Border(*(Side(style="medium"),) * 4)   # 拘束=太枠


def _fill(hex_):
    return PatternFill(start_color=hex_, end_color=hex_, fill_type="solid")


def _day_col(day):
    return _NAME_COLS + day            # C = day 1


def _is_holiday(y, m, d):
    dt = date(y, m, d)
    return jpholiday.is_holiday(dt) or (m == 1 and d in (1, 2, 3))


def render_directiona(grid: dict, *, warnings=None) -> bytes:
    y, m, days = grid["year"], grid["month"], grid["days_in_month"]
    stats_cols = grid["stats_columns"]
    last_col = _NAME_COLS + days + len(stats_cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"勤務分担表{m}月"
    center = Alignment(horizontal="center", vertical="center")

    # Row 1: title, merged to the table width (tracks days; no AH1 hardcode).
    ws.cell(row=1, column=1, value=f"画像診断室 {y}年{m}月 勤務分担表").font = Font(size=14, bold=True)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(row=1, column=1).alignment = center

    # Row 2/3 fixed labels + per-day date/weekday + weekend/holiday column shading.
    ws.cell(row=2, column=1, value="勤務表番号")
    ws.cell(row=2, column=2, value="技師名")
    ws.cell(row=3, column=2, value="曜日")
    for d in range(1, days + 1):
        col = _day_col(d)
        wd = grid["weekdays"][d]
        dc = ws.cell(row=2, column=col, value=d); dc.alignment = center
        wc = ws.cell(row=3, column=col, value=wd); wc.alignment = center
        shade = None
        if wd == "土":
            shade = C_SAT
        elif wd == "日" or _is_holiday(y, m, d):
            shade = C_SUNHOL
        if shade:
            dc.fill = wc.fill = _fill(shade)
    # Stats header labels start right after the day block.
    for i, label in enumerate(stats_cols):
        ws.cell(row=2, column=_NAME_COLS + days + 1 + i, value=label).alignment = center

    _render_body(ws, grid)            # Task 5
    _build_legend_sheet(wb)           # Task 6
    _build_summary_sheet(wb, grid)    # Task 6
    _build_validation_sheet(wb, y, m, warnings)   # Task 7
    _apply_print_setup(ws, last_col)  # Task 7

    ws.freeze_panes = ws.cell(row=_FIRST_DATA_ROW, column=_NAME_COLS + 1).coordinate  # 'C4'

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

Stub the not-yet-built helpers (`_render_body`, `_build_legend_sheet`, `_build_summary_sheet`, `_build_validation_sheet`, `_apply_print_setup`) as no-ops returning immediately, so Task 4 tests pass; flesh them out in Tasks 5–7. (`freeze_panes` is set here so its test in Task 5 already has a target.)

- [ ] **Step 3: Run the Task 4 tests.**

```bash
python -m pytest tests/test_excel_directiona.py -q
```

- [ ] **Step 4: Commit.**

```bash
git add shift_scheduler/src/excel_directiona.py tests/test_excel_directiona.py
git commit  # subject: feat(excel-a): Direction-A skeleton — day-tracking title + weekend/holiday header
```

---

## Task 5: Body — shift-type colour-coding from cell_meta.kind + freeze panes + 拘束 太枠

**Files:** Modify `shift_scheduler/src/excel_directiona.py`, `tests/test_excel_directiona.py`

- [ ] **Step 1: Add failing assertions.**

```python
def test_freeze_panes_locks_name_cols_and_header_rows():
    ws = _load().worksheets[0]
    assert ws.freeze_panes == "C4"


def test_night_cell_is_navy_with_white_font():
    from tests.golden.xlsx_dump import fill_hex
    ws = _load().worksheets[0]
    c = ws.cell(row=4, column=2 + 2)    # T001 day2 = 病CT夜 (kind=night)
    assert c.value == "病CT夜"
    assert fill_hex(c) == "1F3864"
    assert (c.font.color.rgb or "")[-6:] == "FFFFFF"


def test_akemei_grey_off_green_request_italic():
    from tests.golden.xlsx_dump import fill_hex
    ws = _load().worksheets[0]
    assert fill_hex(ws.cell(row=4, column=2 + 3)) == "D9D9D9"   # ○  akemei
    assert fill_hex(ws.cell(row=4, column=2 + 4)) == "E2EFDA"   # 休 off
    assert fill_hex(ws.cell(row=4, column=2 + 5)) == "E2EFDA"   # ☆ special_off
    assert ws.cell(row=4, column=2 + 7).font.italic is True     # 希望休 request


def test_oncall_row_has_thick_duty_border():
    ws = _load().worksheets[0]
    # one row of staff (row4) then the 第1拘束 row at row5
    label = ws.cell(row=5, column=1).value
    assert label == "第1拘束"
    cell = ws.cell(row=5, column=2 + 1)            # 佐藤海 on day 1
    assert cell.value == "佐藤海"
    assert cell.border.left.style == "medium"


def test_stats_block_written_for_working_row():
    ws = _load().worksheets[0]
    # 公休 is the 20th of 21 stats labels -> column = 2 + days + 20
    col = 2 + 7 + (STATS.index("公休") + 1)
    assert ws.cell(row=4, column=col).value == 8
```

- [ ] **Step 2: Implement `_render_body` and `_style_for`.**

```python
def _style_for(kind):
    """(fill_or_None, font_or_None) for a body cell, keyed off kind (Direction-A)."""
    if kind == "night":
        return _fill(C_NIGHT), Font(color="FFFFFF")
    if kind == "akemei":
        return _fill(C_AKEMEI), None
    if kind in ("off", "special_off"):
        return _fill(C_OFF), None
    if kind == "request":
        return None, Font(italic=True)          # 希望休 = 斜体
    return None, None                            # work / empty = 白


def _render_body(ws, grid):
    center = Alignment(horizontal="center", vertical="center")
    days = grid["days_in_month"]
    stats_cols = grid["stats_columns"]
    r = _FIRST_DATA_ROW
    for row in grid["rows"]:
        ws.cell(row=r, column=1, value=row["staff_num"])
        ws.cell(row=r, column=2, value=row["name"])
        for d in range(1, days + 1):
            text = row["cells"].get(d, "")
            kind = row["cell_meta"].get(d, {}).get("kind", "empty")
            c = ws.cell(row=r, column=_day_col(d), value=text)
            c.alignment = center
            fill, font = _style_for(kind)
            if fill: c.fill = fill
            if font: c.font = font
        if row["has_work"] and row["stats"]:
            for i, label in enumerate(stats_cols):
                ws.cell(row=r, column=_NAME_COLS + days + 1 + i,
                        value=row["stats"][label]).alignment = center
        r += 1
    # On-call rows with the 拘束 太枠.
    for oc in grid["oncall_rows"]:
        ws.cell(row=r, column=1, value=oc["label"])
        for d in range(1, days + 1):
            c = ws.cell(row=r, column=_day_col(d), value=oc["cells"].get(d, ""))
            c.alignment = center
            c.border = _DUTY_BORDER
        r += 1
```

- [ ] **Step 3: Run + commit.**

```bash
python -m pytest tests/test_excel_directiona.py -q
git add shift_scheduler/src/excel_directiona.py tests/test_excel_directiona.py
git commit  # subject: feat(excel-a): kind-keyed colour-coding, freeze panes, 拘束 thick border
```

---

## Task 6: 凡例 (legend) sheet + 集計 (summary) sheet

**Files:** Modify `shift_scheduler/src/excel_directiona.py`, `tests/test_excel_directiona.py`

- [ ] **Step 1: Add failing assertions.**

```python
def test_legend_and_summary_sheets_exist():
    wb = _load()
    assert "凡例" in wb.sheetnames
    assert "集計" in wb.sheetnames


def test_legend_explains_symbols_and_colours():
    ws = _load()["凡例"]
    blob = "\n".join(str(c.value) for col in ws.iter_cols() for c in col if c.value)
    for token in ("夜", "明", "(希)", "★", "☆", "17休", "公休"):
        assert token in blob


def test_summary_lists_each_staff_with_key_counts():
    ws = _load()["集計"]
    header = [c.value for c in ws[1]]
    for col in ("技師名", "公休", "夜勤", "代休"):
        assert col in header
    names = [ws.cell(row=r, column=2).value for r in range(2, ws.max_row + 1)]
    assert "佐藤(海)" in names


def test_summary_includes_per_location_columns():
    ws = _load()["集計"]
    header = [c.value for c in ws[1]]
    for loc in ("病CT", "CT", "CLMR"):     # 各場所 from stats_columns
        assert loc in header
```

- [ ] **Step 2: Implement.** 凡例 is static rows mapping symbols + the Direction-A palette swatches to meanings (夜=濃紺, 明け=薄グレー, 公休=薄緑, 希望休=斜体, 土=薄青, 日/祝=薄赤, plus the symbol glossary ★/☆/◆/(希)/17休/○). 集計 is one row per `grid["rows"]` with columns 勤務表番号・技師名・then each `stats_columns` label (covers 公休/夜勤/代休/各場所); for `has_work=False` rows write blanks (mirror the legacy gate). Build via `wb.create_sheet("凡例")` / `wb.create_sheet("集計")`.

- [ ] **Step 3: Run + commit.**

```bash
python -m pytest tests/test_excel_directiona.py -q
git add shift_scheduler/src/excel_directiona.py tests/test_excel_directiona.py
git commit  # subject: feat(excel-a): 凡例 legend sheet + 集計 per-staff summary sheet
```

---

## Task 7: Live-warning validation sheet + A3-landscape print setup

The validation sheet must reflect the **current** roster, not frozen `validation_errors`. The renderer receives a pre-formatted `warnings: list[str]` (the endpoint computes it via `recompute_stats`), keeping the renderer derivation-free.

**Files:** Modify `shift_scheduler/src/excel_directiona.py`, `tests/test_excel_directiona.py`

- [ ] **Step 1: Add failing assertions.**

```python
def test_validation_sheet_renders_passed_warnings():
    wb = openpyxl.load_workbook(BytesIO(render_directiona(
        _sample_grid(), warnings=["6月3日: [CT] の配置人数が不足しています (目標: 2人 / 実際: 1人)"])))
    assert "検証レポート" in wb.sheetnames[-1] or "検証レポート(自動診断)" in wb.sheetnames
    ws = wb["検証レポート(自動診断)"]
    blob = "\n".join(str(c.value) for col in ws.iter_cols() for c in col if c.value)
    assert "[CT] の配置人数が不足" in blob


def test_validation_sheet_clean_when_no_warnings():
    wb = openpyxl.load_workbook(BytesIO(render_directiona(_sample_grid(), warnings=[])))
    ws = wb["検証レポート(自動診断)"]
    blob = "\n".join(str(c.value) for col in ws.iter_cols() for c in col if c.value)
    assert "問題" in blob or "OK" in blob or "なし" in blob   # clean status line


def test_main_sheet_print_setup_a3_landscape():
    ws = _load().worksheets[0]
    assert ws.page_setup.orientation == "landscape"
    assert str(ws.page_setup.paperSize) == str(ws.PAPERSIZE_A3)   # 8
    assert ws.print_title_rows == "1:3"          # header rows repeat
    assert ws.print_title_cols == "A:B"          # name cols repeat
```

- [ ] **Step 2: Implement `_build_validation_sheet`** (sheet name `'検証レポート(自動診断)'`, title merged `A1:E1` to match legacy familiarity; a green clean-status line when `warnings` is empty, else one red row per warning — note §6.5 keeps warning colours **out of the grid**, but the dedicated validation sheet may still colour its own rows) **and `_apply_print_setup`**:

```python
def _apply_print_setup(ws, last_col):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.print_title_rows = "1:3"
    ws.print_title_cols = "A:B"
    ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"
```

- [ ] **Step 3: Run + commit.**

```bash
python -m pytest tests/test_excel_directiona.py -q
git add shift_scheduler/src/excel_directiona.py tests/test_excel_directiona.py
git commit  # subject: feat(excel-a): live recompute_stats validation sheet + A3 landscape print setup
```

---

## Task 8: Serve Direction-A from GET /rosters/{rid}/excel

Wire the endpoint to render Direction-A from the frozen roster. If P2a-2 already added `/rosters/{rid}/excel` returning the current layout, P2c **switches it to Direction-A**; the legacy `ExcelGenerator` remains importable solely for the parity test.

**Files:** Modify `webapp/api/main.py`, add `tests/test_api_excel.py`

> **P2a-2 coupling (verify against actual P2a-2 API):** this task assumes a roster accessor that yields the frozen assignment data needed by `build_grid` + `recompute_stats` — e.g. `store.get_roster(rid)` exposing `technicians, day_assignments, night_assignments, requests, on_call_assignments, off_counts, daikyu_counts, locations, year, month, daily_location_needs, target_holidays`. Adapt the names below to P2a-2's real roster model; the rendering call sequence is the invariant.

- [ ] **Step 1: Write the endpoint test** (uses `TestClient`; seed a roster the same way `tests/test_api.py` seeds jobs/rosters — reuse its fixture/monkeypatch helper).

```python
# tests/test_api_excel.py
from io import BytesIO
import openpyxl
from fastapi.testclient import TestClient
from webapp.api.main import app

client = TestClient(app)


def test_rosters_excel_returns_direction_a_workbook(seeded_roster):   # fixture: see test_api.py
    rid = seeded_roster.id
    resp = client.get(f"/rosters/{rid}/excel")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in resp.headers["content-disposition"]
    wb = openpyxl.load_workbook(BytesIO(resp.content))
    assert wb.worksheets[0].title.startswith("勤務")     # Direction-A main sheet
    assert "凡例" in wb.sheetnames and "集計" in wb.sheetnames
    assert wb.worksheets[0].freeze_panes == "C4"         # Direction-A, not legacy


def test_rosters_excel_404_for_unknown():
    assert client.get("/rosters/does-not-exist/excel").status_code == 404
```

- [ ] **Step 2: Implement the handler** (mirror the existing `/jobs/{job_id}/excel` Response/Content-Disposition pattern at `webapp/api/main.py:53`).

```python
from shift_scheduler.src import grid_derivation
from shift_scheduler.src import stats_engine
from shift_scheduler.src.excel_directiona import render_directiona

def _format_warnings(rc: dict, month: int) -> list[str]:
    out = []
    for u in rc["understaffing"]:
        out.append(f"{month}月{u['day']}日: [{u['loc']}] の配置人数が不足しています "
                   f"(目標: {u['required']}人 / 実際: {u['assigned']}人)")
    for day in rc["night_hb_gaps"]:
        out.append(f"{month}月{day}日: 夜勤メンバーにHB対応可能者がいないため代替処理を行いました")
    return out

@app.get("/rosters/{rid}/excel")
def get_roster_excel(rid: str):
    r = store.get_roster(rid)
    if r is None:
        raise HTTPException(status_code=404, detail="roster not found")
    grid = grid_derivation.build_grid(
        year=r.year, month=r.month, technicians=r.technicians,
        day_assignments=r.day_assignments, night_assignments=r.night_assignments,
        requests=r.requests, off_counts=r.off_counts, daikyu_counts=r.daikyu_counts,
        on_call_assignments=r.on_call_assignments,
    )
    rc = stats_engine.recompute_stats(
        r.assignments, r.requests, r.night_assignments, r.technicians, r.locations,
        r.year, r.month, r.target_holidays, daily_location_needs=r.daily_location_needs,
    )
    xlsx = render_directiona(grid, warnings=_format_warnings(rc, r.month))
    filename = f"勤務表_{r.year}年{r.month}月.xlsx"
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(content=xlsx,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": disposition})
```

- [ ] **Step 3: Run the API + full suite.**

```bash
python -m pytest tests/test_api_excel.py tests/test_api.py -q
python -m pytest -q
```

- [ ] **Step 4: Commit.**

```bash
git add webapp/api/main.py tests/test_api_excel.py
git commit  # subject: feat(api): serve Direction-A Excel from GET /rosters/{rid}/excel
```

---

## Self-Review

**Spec §6.5 coverage map** (every bullet → task):

| §6.5 requirement | Where |
|---|---|
| タイトル幅が当月日数に自動追従（AH1固定バグ解消） | Task 4 `test_title_merge_width_tracks_days_plus_offset` |
| 2段ヘッダ（日付＋曜日） | Task 4 `test_two_row_header_dates_then_weekdays` |
| 行＝技師（既定マスタ順、build_grid 行順を保持） | Task 5 `_render_body` iterates `grid["rows"]` as-is |
| 固定ペイン（氏名列＋ヘッダ） | Task 5 `test_freeze_panes_locks_name_cols_and_header_rows` (`C4`) |
| 右側集計ブロック＋別シート集計 | Task 5 stats block + Task 6 集計 sheet |
| 夜勤＝濃紺＋白字 | Task 5 `test_night_cell_is_navy_with_white_font` |
| 明け＝薄グレー / 公休＝薄緑 / 希望休＝斜体 | Task 5 `test_akemei_grey_off_green_request_italic` |
| 拘束＝太枠 | Task 5 `test_oncall_row_has_thick_duty_border` |
| 日勤＝白（場所別淡色は任意） | Task 5 `_style_for` returns no fill for `work`; per-location tint deferred (optional) |
| 土＝薄青 / 日祝＝薄赤（jpholiday） | Task 4 `test_weekend_and_holiday_columns_are_shaded` |
| 警告色はExcel本体に出さない | Tasks 5–7: grid cells never warning-coloured; warnings only on validation sheet |
| 凡例シート | Task 6 `test_legend_explains_symbols_and_colours` |
| 集計シート（個人別） | Task 6 `test_summary_lists_each_staff_with_key_counts` |
| 検証レポートシート保持（現行同様） | Task 7 `_build_validation_sheet` (live warnings) |
| 印刷：A3横・印刷タイトル行 | Task 7 `test_main_sheet_print_setup_a3_landscape` |
| 統計ラベル/パーサ単一ソース化 | Tasks 3–7 consume `build_grid["stats_columns"]`; no re-declaration |
| 新レンダラも決定的 | No clocks/RNG; pure dict→openpyxl; covered implicitly by stable tests |
| 突合は技師IDキー（並び順非依存） | Parity test (Task 2) keyed off the dump; build_grid carries `staff_id` |

**Byte-identity proof** (legacy refactor): Tasks 1→2→3 capture a normalized dump of the CURRENT output, characterize it green, then refactor under that green test — so the `build_grid` migration cannot silently change today's `.xlsx`. Fills stay keyed off `cell_meta.fill` (text-driven), per the migration caveat.

**Placeholder scan:** before final commit, `grep -rn "TODO\|FIXME\|pass  # stub\|raise NotImplementedError" shift_scheduler/src/excel_directiona.py` must be empty — the Task-4 no-op stubs for `_render_body`/`_build_legend_sheet`/`_build_summary_sheet`/`_build_validation_sheet`/`_apply_print_setup` are all replaced by Tasks 5–7.

**Type consistency:** `build_grid` day keys are `int`; the parity fixture JSON stringifies them, so `tests/test_excel_parity.py` re-ints via `_int_days`. `cell_meta[day]["fill"]` is a 6-char hex or `None`; `_style_for` keys off the `str` `kind`. `off_counts` may be `float` (e.g. 9.5) — the dump/stub round-trips it as-is. `stats` is `None` for `has_work=False` rows — both renderers guard on it.

---

## Next

After P2c: P2d wires the React grid (`docs/superpowers/plans/2026-06-29-web-app-p2d-react.md`) to the same `build_grid` dict (it consumes `cell_meta.kind`/`.fill` for CSS and `stats` for the side panel), and the edit endpoints (P2a-2) re-render Direction-A on download. When P2a-2 lands, **verify the three assumptions flagged in the build_grid-shape report** (holiday shading source, roster accessor shape, `recompute_stats` warning fields) against its actual output and adjust Tasks 7–8 if needed.
