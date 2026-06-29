# Web App P1 — Backend Foundation & Excel Data-Parity Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the existing scheduler into a callable `run_schedule()` that returns structured results plus Excel bytes, lock its behaviour with a determinism/parity golden test, and expose it through a minimal FastAPI async-job API with an Excel download — the backend foundation every later phase builds on.

**Architecture:** Add a thin `run_schedule()` function inside the existing `main.py` (no helper functions move — lowest-risk extraction) returning a new `ScheduleResult`. `main()` becomes a CLI shim that calls it. A separate `webapp/api` FastAPI app runs generation as a background job, serialised through a single-worker lock to preserve CP-SAT determinism, and serves the result JSON and the `.xlsx`.

**Tech Stack:** Python 3.13, OR-Tools (existing), openpyxl (existing), FastAPI, Uvicorn, pytest, httpx (FastAPI `TestClient`).

**Scope note:** P1 is backend-only and reuses the **current** Excel layout (the Direction-A redesign from spec §6.5 is a later plan). The acceptance gate is **schedule-data parity** (assignments / off / 代休 / validation), not byte-identical Excel. Masters stay as the on-disk CSVs in `shift_scheduler/data/` (SQLite master CRUD is P3). No auth, no editing, no React yet.

---

## File Structure

- Create `shift_scheduler/src/models/schedule_result.py` — `ScheduleResult` dataclass + `as_dict()` (JSON-able, deterministic) used by the API and the parity test.
- Modify `shift_scheduler/src/excel_generator.py` — add `generate_bytes()`; make `generate()` accept a path **or** a binary stream.
- Modify `main.py` — add `run_schedule(...)`; slim `main()` to a CLI shim; fix the swallow-and-continue loader `except`.
- Create `pytest.ini` — register the `slow` marker (real-solver tests).
- Create `tests/test_excel_bytes.py` — unit test for `generate_bytes()`.
- Create `tests/test_run_schedule.py` — integration test (`@pytest.mark.slow`).
- Create `tests/golden/2026-06_assignments.json` — frozen reference snapshot.
- Create `tests/test_parity_golden.py` — determinism/parity gate (`@pytest.mark.slow`).
- Create `webapp/__init__.py`, `webapp/api/__init__.py`, `webapp/api/config.py`, `webapp/api/jobs.py`, `webapp/api/main.py` — FastAPI app + job runner.
- Create `webapp/requirements.txt` — web deps.
- Create `tests/test_api.py` — API tests with a mocked runner (fast).
- Create `webapp/README.md` — how to run the API locally.

All commands assume the repo root `"/Users/kohei/Desktop/local-shift ver1"` is the working directory and the venv is active (`source .venv/bin/activate`).

---

## Task 1: `ExcelGenerator.generate_bytes()` + stream-friendly `generate()`

**Files:**
- Modify: `shift_scheduler/src/excel_generator.py:50-62`
- Test: `tests/test_excel_bytes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_excel_bytes.py
from io import BytesIO
import openpyxl
from shift_scheduler.src.excel_generator import ExcelGenerator


def _empty_generator():
    # technicians=[] -> no staff rows, no Staff object needed.
    return ExcelGenerator(
        year=2026, month=6, technicians=[],
        night_assignments={}, day_assignments={}, requests={},
    )


def test_generate_bytes_returns_valid_xlsx():
    data = _empty_generator().generate_bytes()
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
    wb = openpyxl.load_workbook(BytesIO(data))
    assert "6月勤務表" in wb.sheetnames
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_excel_bytes.py -v`
Expected: FAIL with `AttributeError: 'ExcelGenerator' object has no attribute 'generate_bytes'`.

- [ ] **Step 3: Write minimal implementation**

In `shift_scheduler/src/excel_generator.py`, change the `generate` method signature/print and add `generate_bytes` right after it:

```python
    def generate(self, target):
        """Excel生成。target はファイルパス(str)またはバイナリストリーム。"""
        self._create_header()
        self._create_day_header()
        self._create_weekday_row()
        self._fill_assignments()
        self._apply_formatting()

        if self.validation_errors is not None:
            self._create_validation_report_sheet()

        self.wb.save(target)
        if isinstance(target, str):
            print(f"✓ 勤務表を保存: {target}")

    def generate_bytes(self) -> bytes:
        """レンダリング結果を .xlsx バイト列で返す（Web配信・凍結保存用）。"""
        from io import BytesIO
        buf = BytesIO()
        self.generate(buf)
        return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_excel_bytes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/excel_generator.py tests/test_excel_bytes.py
git commit -m "feat(excel): add generate_bytes() and stream-friendly generate()"
```

---

## Task 2: `ScheduleResult` dataclass

**Files:**
- Create: `shift_scheduler/src/models/schedule_result.py`
- Test: `tests/test_schedule_result.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schedule_result.py
from shift_scheduler.src.models.schedule_result import ScheduleResult


def _sample():
    return ScheduleResult(
        year=2026, month=6,
        staff=[{"id": "T002", "name": "B"}, {"id": "T001", "name": "A"}],
        day_assignments={2: {"CT": ["T002", "T001"]}},
        night_assignments={3: ["T002", "T001"]},
        requests={1: {"T001": "☆"}},
        on_call_assignments={5: {"第1拘束": "T001"}},
        daikyu_counts={"T001": 0},
        off_counts={"T001": 9},
        validation_errors=["x"],
        workbook_bytes=b"PK\x03\x04",
    )


def test_as_dict_excludes_bytes_and_is_deterministic():
    d = _sample().as_dict()
    assert "workbook_bytes" not in d
    # staff-id lists are sorted so ordering never causes false parity mismatches
    assert d["day_assignments"]["2"]["CT"] == ["T001", "T002"]
    assert d["night_assignments"]["3"] == ["T001", "T002"]
    # integer day keys are stringified for stable JSON round-tripping
    assert set(d["requests"].keys()) == {"1"}
    assert d["year"] == 2026 and d["month"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schedule_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shift_scheduler.src.models.schedule_result'`.

- [ ] **Step 3: Write minimal implementation**

```python
# shift_scheduler/src/models/schedule_result.py
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ScheduleResult:
    """run_schedule() の構造化結果。workbook_bytes 以外は JSON 化可能。"""
    year: int
    month: int
    staff: List[Dict[str, str]]                       # [{"id","name"}], 技師マスタ順
    day_assignments: Dict[int, Dict[str, List[str]]]  # {day: {loc_code: [staff_id]}}
    night_assignments: Dict[int, List[str]]           # {day: [staff_id]}
    requests: Dict[int, Dict[str, str]]               # {day: {staff_id: symbol}}
    on_call_assignments: Dict                          # {day: {第1拘束/第2拘束: staff_id}}
    daikyu_counts: Dict[str, int]
    off_counts: Dict[str, int]
    validation_errors: List[str]
    workbook_bytes: bytes = b""

    def as_dict(self) -> dict:
        """決定的・JSON 化可能な辞書（workbook_bytes は除外、リストはソート）。"""
        return {
            "year": self.year,
            "month": self.month,
            "staff": self.staff,
            "day_assignments": {
                str(d): {loc: sorted(ids) for loc, ids in locs.items()}
                for d, locs in self.day_assignments.items()
            },
            "night_assignments": {
                str(d): sorted(ids) for d, ids in self.night_assignments.items()
            },
            "requests": {
                str(d): dict(sm) for d, sm in self.requests.items()
            },
            "on_call_assignments": {
                str(d): v for d, v in self.on_call_assignments.items()
            },
            "daikyu_counts": dict(self.daikyu_counts),
            "off_counts": dict(self.off_counts),
            "validation_errors": list(self.validation_errors),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schedule_result.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shift_scheduler/src/models/schedule_result.py tests/test_schedule_result.py
git commit -m "feat(model): add ScheduleResult with deterministic as_dict()"
```

---

## Task 3: Extract `run_schedule()` in `main.py`; slim `main()`

**Files:**
- Modify: `main.py:1117-1435` (replace `main()`; add `run_schedule()` before it)
- Test: `tests/test_run_schedule.py`

This is a **mechanical extraction**: the body currently in `main()` (`main.py:1134-1427`) moves into a new `run_schedule()` with four precise changes:
1. Parameters replace argparse: use `data_dir` / `output_dir` instead of `args.data_dir` / `args.output_dir`.
2. Fix the swallow-and-continue loader bug (`main.py:1139-1174`): drop the bare `try/except` and let load errors raise.
3. Replace the final `generator.generate(output_path)` block (`main.py:1410-1428`) with: render once to bytes, write the file only when `output_dir` is given.
4. Return a `ScheduleResult`. Keep all `print(...)` calls (worker captures stdout; the logging refactor is a later phase).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_schedule.py
import openpyxl
from io import BytesIO
import pytest

from main import run_schedule
from shift_scheduler.src.models.schedule_result import ScheduleResult

DATA_DIR = "shift_scheduler/data"


@pytest.mark.slow
def test_run_schedule_returns_populated_result():
    result = run_schedule(2026, 6, data_dir=DATA_DIR)  # output_dir omitted -> no file write
    assert isinstance(result, ScheduleResult)
    assert result.year == 2026 and result.month == 6
    assert len(result.staff) > 0
    assert len(result.day_assignments) > 0          # at least some days placed
    assert isinstance(result.off_counts, dict) and len(result.off_counts) > 0
    # bytes form a valid workbook
    wb = openpyxl.load_workbook(BytesIO(result.workbook_bytes))
    assert "6月勤務表" in wb.sheetnames
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_schedule.py -v -m slow`
Expected: FAIL with `ImportError: cannot import name 'run_schedule' from 'main'`.

- [ ] **Step 3: Add `run_schedule()` and slim `main()`**

At the top of `main.py`, add the imports:

```python
from io import BytesIO
from shift_scheduler.src.models.schedule_result import ScheduleResult
```

Add this function immediately **before** `def main():` (`main.py:1117`). It is the current `main()` body (`main.py:1134-1428`) with the four changes applied:

```python
def run_schedule(year: int, month: int, data_dir: str = "shift_scheduler/data",
                 output_dir: str | None = None, *, target_holidays: int | None = None) -> ScheduleResult:
    """勤務表を生成して構造化結果を返す（CLI/Web 共通の呼び出し口）。

    output_dir を指定すると現行レイアウトの .xlsx も書き出す（CLI 用）。
    ロジックは既存スケジューラを無改造で使う（決定性 seed=42 / num_workers=1 維持）。
    """
    year_month = f"{year}-{month:02d}"

    print("=" * 70, flush=True)
    print(f"勤務表作成システム - {year}年{month}月", flush=True)
    print("=" * 70, flush=True)

    # ── データ読み込み（失敗時は例外を伝播：握り潰さない）──
    print("📂 データ読み込み中...", flush=True)
    loader = DataLoader(data_dir=data_dir)
    staff_list, locations, skills, requests, rules, pb_rules = loader.load_all(year_month)
    name_to_id = {s.name: s.id for s in staff_list}
    night_counts = loader.load_night_counts(year_month, name_to_id=name_to_id)

    technicians = staff_list
    special_rules = rules
    training_rules = loader.load_training_rules(technicians)

    # ── 夜勤スキル導出 → 前月夜勤実績 → 夜勤スケジューリング ──
    night_skills = NightSkillDeriver.derive(skills)
    start_date = date(year, month, 1)
    prev_month_limit = start_date - timedelta(days=7)
    prev_night_history = [
        NightAssignment(date=r.date, staff_id=r.staff_id, role='History')
        for r in requests
        if prev_month_limit <= r.date < start_date and '夜' in r.symbol
    ]
    night_scheduler = NightScheduler(staff_list=technicians, year=year, month=month)
    night_result = night_scheduler.schedule(requests, night_counts, prev_night_history)

    night_assignments_dict = {}
    for na in night_result:
        night_assignments_dict.setdefault(na.date.day, []).append(na.staff_id)
    full_night_assignments = night_result + prev_night_history

    if target_holidays is None:
        target_holidays = loader.load_monthly_holidays(year, month)

    # ── Phase 1/2/2.5/2.6 ──（既存ヘルパをそのまま呼ぶ）
    pre_seeded = pre_seed_rest_days(
        technicians=technicians, requests=requests, night_assignments=full_night_assignments,
        year=year, month=month, target_holidays=target_holidays, skills=skills, locations=locations,
    )
    requests_with_preseed = requests + pre_seeded
    day_scheduler = DayScheduler(
        staff_list=technicians, skills=skills, locations=locations, pb_rules=pb_rules,
        rules=special_rules, training_rules=training_rules, year=year, month=month,
        disable_training=True, target_holidays=target_holidays,
    )
    day_result_list, daily_location_needs = day_scheduler.schedule(requests_with_preseed, full_night_assignments)
    day_result_list = rebalance_workload(
        day_result_list=day_result_list, technicians=technicians, skills=skills, locations=locations,
        requests=requests_with_preseed, night_assignments=full_night_assignments,
        year=year, month=month, target_holidays=target_holidays,
    )
    day_result_list = optimize_assignments_cpsat(
        day_result_list=day_result_list, technicians=technicians, skills=skills, locations=locations,
        requests=requests_with_preseed, night_assignments=full_night_assignments,
        year=year, month=month, target_holidays=target_holidays,
    )
    day_result_list, daikyu_counts, off_counts = assign_monthly_off_days(
        technicians=technicians, day_result_list=day_result_list, night_assignments=full_night_assignments,
        requests=requests_with_preseed, year=year, month=month, target_holidays=target_holidays,
    )

    # ── 拘束（オンコール）──
    from shift_scheduler.src.schedulers.oncall_scheduler import OnCallScheduler
    oncall_scheduler = OnCallScheduler(staff_list=technicians, year=year, month=month)
    on_call_assignments, on_call_counts = oncall_scheduler.schedule(
        day_result_list, full_night_assignments, requests)

    # ── 出力用辞書へ変換 ──
    day_assignments_dict = {}
    for da in day_result_list:
        if da.date.month != month:
            continue
        day_assignments_dict.setdefault(da.date.day, {}).setdefault(da.location_code, []).append(da.staff_id)

    requests_dict = {}
    for r in requests_with_preseed:
        if r.date.year == year and r.date.month == month:
            slot = requests_dict.setdefault(r.date.day, {})
            if r.staff_id not in slot:
                slot[r.staff_id] = r.symbol

    # ── 検証 ──
    validation_errors = []
    for d, loc_needs in daily_location_needs.items():
        for loc_code, required in loc_needs.items():
            if loc_code.startswith('(') and loc_code.endswith(')'):
                continue
            if required > 0:
                assigned = len(day_assignments_dict.get(d.day, {}).get(loc_code, []))
                if assigned < required:
                    validation_errors.append(
                        f"{d.month}月{d.day}日: [{loc_code}] の配置人数が不足しています (目標: {required}人 / 実際: {assigned}人)")
    for d_day, assigns in night_assignments_dict.items():
        night_staff_objs = [s for s in technicians if s.id in assigns]
        if not any(getattr(s, 'night_hb', False) for s in night_staff_objs):
            validation_errors.append(
                f"{month}月{d_day}日: 夜勤メンバーにHB対応可能者がいないため代替処理を行いました (※本日の拘束枠でHBカバー)")

    # ── クL 表示オーバーレイ ──（現行 main.py:1376-1407 をそのまま移植）
    from shift_scheduler.src.models.skill import SkillRank as _SR
    _staff_by_id = {t.id: t for t in technicians}

    def _can_lead_clinic(sid):
        ssk = skills.get(sid, {})
        if 'クL' in ssk:
            return ssk.get('クL', _SR.NONE) > _SR.NONE
        t = _staff_by_id.get(sid)
        if not t or t.gender.value != '女':
            return False
        if int(t.experience_years) < 3:
            return False
        return ssk.get('ク', _SR.NONE) > _SR.NONE

    _kl_counts = {}
    for _d in sorted(day_assignments_dict.keys()):
        _ku = day_assignments_dict[_d].get('ク', [])
        _elig = [sid for sid in _ku if _can_lead_clinic(sid)]
        if not _elig:
            continue
        _leader = min(_elig, key=lambda s: (_kl_counts.get(s, 0), s))
        day_assignments_dict[_d]['ク'].remove(_leader)
        if not day_assignments_dict[_d]['ク']:
            del day_assignments_dict[_d]['ク']
        day_assignments_dict[_d].setdefault('クL', []).append(_leader)
        _kl_counts[_leader] = _kl_counts.get(_leader, 0) + 1

    # ── Excel（現行レイアウト）→ bytes、必要なら file ──
    generator = ExcelGenerator(
        year=year, month=month, technicians=technicians,
        night_assignments=night_assignments_dict, day_assignments=day_assignments_dict,
        requests=requests_dict, on_call_assignments=on_call_assignments,
        name_mapper=None, daikyu_counts=daikyu_counts, off_counts=off_counts,
        validation_errors=validation_errors,
    )
    workbook_bytes = generator.generate_bytes()
    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)
        with open(f"{output_dir}/勤務表_{year}年{month}月.xlsx", "wb") as f:
            f.write(workbook_bytes)

    return ScheduleResult(
        year=year, month=month,
        staff=[{"id": t.id, "name": t.name} for t in technicians],
        day_assignments=day_assignments_dict,
        night_assignments=night_assignments_dict,
        requests=requests_dict,
        on_call_assignments=on_call_assignments,
        daikyu_counts=daikyu_counts, off_counts=off_counts,
        validation_errors=validation_errors,
        workbook_bytes=workbook_bytes,
    )
```

Then replace `def main():` body (everything from `main.py:1118` `parser = ...` through `main.py:1432`) with this shim:

```python
def main():
    parser = argparse.ArgumentParser(description='勤務表自動作成システム')
    parser.add_argument('--year', type=int, required=True, help='年（例: 2026）')
    parser.add_argument('--month', type=int, required=True, help='月（例: 1）')
    parser.add_argument('--data-dir', default='shift_scheduler/data', help='データディレクトリ')
    parser.add_argument('--output-dir', default='output', help='出力ディレクトリ')
    args = parser.parse_args()

    run_schedule(args.year, args.month, data_dir=args.data_dir, output_dir=args.output_dir)

    print("=" * 70, flush=True)
    print("✅ 勤務表作成完了", flush=True)
    print("=" * 70, flush=True)
```

- [ ] **Step 4: Run the integration test**

Run: `python -m pytest tests/test_run_schedule.py -v -m slow`
Expected: PASS (takes 1–several minutes — it runs the real solver).

- [ ] **Step 5: Verify the CLI still works end-to-end**

Run: `python main.py --year 2026 --month 6`
Expected: prints the pipeline log and writes `output/勤務表_2026年6月.xlsx`.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_run_schedule.py
git commit -m "refactor(main): extract run_schedule() returning ScheduleResult; main() is now a CLI shim"
```

---

## Task 4: Determinism / data-parity golden gate

**Files:**
- Create: `pytest.ini`
- Create: `tests/golden/2026-06_assignments.json` (generated)
- Test: `tests/test_parity_golden.py`

- [ ] **Step 1: Register the `slow` marker**

```ini
# pytest.ini
[pytest]
markers =
    slow: end-to-end tests that run the real CP-SAT solver (minutes)
```

- [ ] **Step 2: Write the parity test (fails: golden missing)**

```python
# tests/test_parity_golden.py
import json
import os
import pytest

from main import run_schedule

DATA_DIR = "shift_scheduler/data"
GOLDEN = "tests/golden/2026-06_assignments.json"


@pytest.mark.slow
def test_run_schedule_matches_golden_snapshot():
    assert os.path.exists(GOLDEN), "golden snapshot missing — generate it (see plan Task 4 Step 4)"
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    actual = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    # round-trip through json so int/str key handling matches the stored file
    actual = json.loads(json.dumps(actual, ensure_ascii=False, sort_keys=True))
    expected = json.loads(json.dumps(expected, ensure_ascii=False, sort_keys=True))
    assert actual == expected


@pytest.mark.slow
def test_run_schedule_is_deterministic_across_two_runs():
    a = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    b = run_schedule(2026, 6, data_dir=DATA_DIR).as_dict()
    assert a == b
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_parity_golden.py -v -m slow`
Expected: FAIL on `test_..._matches_golden_snapshot` (golden missing).

- [ ] **Step 4: Generate the golden snapshot from the current pipeline**

```bash
mkdir -p tests/golden
python -c "import json; from main import run_schedule; \
open('tests/golden/2026-06_assignments.json','w',encoding='utf-8').write(\
json.dumps(run_schedule(2026,6,data_dir='shift_scheduler/data').as_dict(), ensure_ascii=False, sort_keys=True, indent=2))"
```

Manually sanity-check the file: it should contain non-empty `day_assignments`, `off_counts`, etc.

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_parity_golden.py -v -m slow`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add pytest.ini tests/test_parity_golden.py tests/golden/2026-06_assignments.json
git commit -m "test(parity): freeze 2026-06 schedule as golden; assert determinism"
```

---

## Task 5: webapp package + FastAPI app + `GET /health`

**Files:**
- Create: `webapp/requirements.txt`, `webapp/__init__.py`, `webapp/api/__init__.py`, `webapp/api/config.py`, `webapp/api/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add web deps and install**

```text
# webapp/requirements.txt
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
```

Run: `pip install -r webapp/requirements.txt`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from webapp.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'webapp'`.

- [ ] **Step 4: Create the package files**

```python
# webapp/__init__.py
```
```python
# webapp/api/__init__.py
```
```python
# webapp/api/config.py
import os


class Settings:
    # P1: masters are the on-disk CSVs (SQLite master store is P3).
    data_dir: str = os.environ.get("SHIFT_DATA_DIR", "shift_scheduler/data")


settings = Settings()
```
```python
# webapp/api/main.py
from fastapi import FastAPI

app = FastAPI(title="勤務表 Web API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add webapp/ tests/test_api.py
git commit -m "feat(api): FastAPI app skeleton with /health"
```

---

## Task 6: Async generation job — `POST /jobs`, `GET /jobs/{id}`

**Files:**
- Create: `webapp/api/jobs.py`
- Modify: `webapp/api/main.py`
- Test: `tests/test_api.py` (extend)

The job runner is injected (`RUNNER` defaults to `run_schedule`) so tests use a fast fake. A module-level lock serialises real solves to protect CP-SAT determinism and the host CPU.

- [ ] **Step 1: Write the failing test (extend `tests/test_api.py`)**

```python
# append to tests/test_api.py
from shift_scheduler.src.models.schedule_result import ScheduleResult
import webapp.api.main as api_main


def _fake_runner(year, month, data_dir):
    return ScheduleResult(
        year=year, month=month, staff=[{"id": "T001", "name": "A"}],
        day_assignments={1: {"CT": ["T001"]}}, night_assignments={},
        requests={}, on_call_assignments={}, daikyu_counts={"T001": 0},
        off_counts={"T001": 9}, validation_errors=[], workbook_bytes=b"PK\x03\x04",
    )


def test_create_and_fetch_job(monkeypatch):
    monkeypatch.setattr(api_main, "RUNNER", _fake_runner)
    r = client.post("/jobs", json={"year": 2026, "month": 6})
    assert r.status_code == 201
    job_id = r.json()["id"]
    # TestClient runs BackgroundTasks synchronously, so the job is already done
    s = client.get(f"/jobs/{job_id}")
    assert s.status_code == 200
    assert s.json()["status"] == "done"


def test_invalid_month_rejected():
    r = client.post("/jobs", json={"year": 2026, "month": 13})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL (`/jobs` not found → 404, and `RUNNER` attribute missing).

- [ ] **Step 3: Implement the job store**

```python
# webapp/api/jobs.py
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

from shift_scheduler.src.models.schedule_result import ScheduleResult


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


@dataclass
class Job:
    id: str
    year: int
    month: int
    status: JobStatus = JobStatus.queued
    error: Optional[str] = None
    result: Optional[ScheduleResult] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, year: int, month: int) -> Job:
        job = Job(id=uuid.uuid4().hex, year=year, month=month)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


# Serialise real solves: protects CP-SAT determinism (num_workers=1) and CPU.
_solve_lock = threading.Lock()


def run_job(store: JobStore, job_id: str, runner: Callable, data_dir: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    with _solve_lock:
        job.status = JobStatus.running
        try:
            job.result = runner(job.year, job.month, data_dir)
            job.status = JobStatus.done
        except Exception as exc:  # surface failures as a failed job, not a 500
            job.error = str(exc)
            job.status = JobStatus.failed
```

- [ ] **Step 4: Wire the routes into `webapp/api/main.py`**

```python
# webapp/api/main.py
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, conint

from webapp.api.config import settings
from webapp.api.jobs import JobStore, run_job
from main import run_schedule

app = FastAPI(title="勤務表 Web API", version="0.1.0")
store = JobStore()
RUNNER = run_schedule  # indirection so tests can monkeypatch a fast fake


class JobRequest(BaseModel):
    year: conint(ge=2000, le=2100)
    month: conint(ge=1, le=12)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=201)
def create_job(req: JobRequest, background: BackgroundTasks):
    job = store.create(req.year, req.month)
    background.add_task(run_job, store, job.id, RUNNER, settings.data_dir)
    return {"id": job.id, "status": job.status}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"id": job.id, "year": job.year, "month": job.month,
            "status": job.status, "error": job.error}
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS (all four API tests).

- [ ] **Step 6: Commit**

```bash
git add webapp/api/jobs.py webapp/api/main.py tests/test_api.py
git commit -m "feat(api): async generation jobs with single-worker solve lock"
```

---

## Task 7: Result JSON + Excel download — `GET /jobs/{id}/result`, `GET /jobs/{id}/excel`

**Files:**
- Modify: `webapp/api/main.py`
- Test: `tests/test_api.py` (extend)

- [ ] **Step 1: Write the failing test (extend `tests/test_api.py`)**

```python
# append to tests/test_api.py
def test_result_and_excel_download(monkeypatch):
    monkeypatch.setattr(api_main, "RUNNER", _fake_runner)
    job_id = client.post("/jobs", json={"year": 2026, "month": 6}).json()["id"]

    res = client.get(f"/jobs/{job_id}/result")
    assert res.status_code == 200
    body = res.json()
    assert body["day_assignments"]["1"]["CT"] == ["T001"]
    assert body["off_counts"]["T001"] == 9
    assert "workbook_bytes" not in body

    xl = client.get(f"/jobs/{job_id}/excel")
    assert xl.status_code == 200
    assert xl.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert xl.content == b"PK\x03\x04"


def test_result_404_when_missing():
    assert client.get("/jobs/deadbeef/result").status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL (result/excel routes 404).

- [ ] **Step 3: Add the two routes to `webapp/api/main.py`**

```python
# add near the other imports
from fastapi import Response


# add these routes
def _require_done(job_id: str):
    job = store.get(job_id)
    if job is None or job.result is None:
        raise HTTPException(status_code=404, detail="result not available")
    return job


@app.get("/jobs/{job_id}/result")
def get_result(job_id: str):
    return _require_done(job_id).result.as_dict()


@app.get("/jobs/{job_id}/excel")
def get_excel(job_id: str):
    job = _require_done(job_id)
    filename = f"勤務表_{job.year}年{job.month}月.xlsx"
    return Response(
        content=job.result.workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full fast suite (no slow solves)**

Run: `python -m pytest -m "not slow" -v`
Expected: PASS for `test_excel_bytes.py`, `test_schedule_result.py`, `test_api.py`.

- [ ] **Step 6: Commit**

```bash
git add webapp/api/main.py tests/test_api.py
git commit -m "feat(api): result JSON and Excel download endpoints"
```

---

## Task 8: Run docs (`webapp/README.md`)

**Files:**
- Create: `webapp/README.md`

- [ ] **Step 1: Write the README**

````markdown
# 勤務表 Web API (P1 backend foundation)

## セットアップ
```bash
source .venv/bin/activate
pip install -r webapp/requirements.txt
```

## 起動
```bash
uvicorn webapp.api.main:app --reload --port 8000
```

## 使い方（手動確認）
1. `POST http://localhost:8000/jobs`  body: `{"year":2026,"month":6}` → `{"id":"...","status":"queued"}`
2. `GET http://localhost:8000/jobs/{id}` → `status` が `done` になるまでポーリング（実ソルバーで数分）
3. `GET http://localhost:8000/jobs/{id}/result` → 配置 JSON
4. `GET http://localhost:8000/jobs/{id}/excel` → 現行レイアウトの .xlsx ダウンロード

データは環境変数 `SHIFT_DATA_DIR`（既定 `shift_scheduler/data`）から読む。
P1 はマスタを CSV のまま使い、認証・手修正・新レイアウトは後続フェーズ。

## テスト
```bash
python -m pytest -m "not slow" -v   # 高速（モック）
python -m pytest -m slow -v         # 実ソルバー（数分）：抽出・決定性・パリティ
```
````

- [ ] **Step 2: Commit**

```bash
git add webapp/README.md
git commit -m "docs(webapp): P1 run + test instructions"
```

---

## Self-Review

**Spec coverage (P1 slice of spec §12):**
- run_schedule extraction → Task 3. ✅
- ScheduleResult structured return → Task 2/3. ✅
- BytesIO Excel → Task 1. ✅
- Determinism preserved + data-parity gate (spec §6 acceptance, "byte→data parity") → Task 4. ✅
- Async generation job + status → Task 6. ✅
- Result display + Excel download → Task 7. ✅
- Loader swallow-and-continue fix (spec §11.6) → Task 3 Step 3 change #2. ✅
- year/month validation (spec §11.7) → Task 6 (`conint`). ✅
- Materialize-from-SQLite, master CRUD, manual edit, heatmap, auth, Direction-A Excel redesign → **deferred to P2–P5 plans** (out of P1 scope, stated in header).

**Placeholder scan:** none — every code/command step is concrete.

**Type consistency:** `run_schedule(year, month, data_dir=..., output_dir=None, *, target_holidays=None)` and `ScheduleResult` field names (`day_assignments`, `night_assignments`, `requests`, `on_call_assignments`, `daikyu_counts`, `off_counts`, `validation_errors`, `workbook_bytes`, `staff`) are used identically in Tasks 2, 3, 6, 7. `as_dict()` stringifies day keys and sorts id lists — tests in Tasks 2/4/7 rely on that. `RUNNER` indirection name matches the monkeypatch in Tasks 6/7.

---

## Next phases (outline — separate plans)
- **P2:** Direction-A Excel redesign (spec §6.5) + React grid, manual-edit model + 3 live warnings, partial-lock re-solve.
- **P3:** SQLite master store + materialize step + master CRUD with the hardcoded-staff-ID safety gate (spec §9).
- **P4:** heatmap, dashboards.
- **P5:** auth, confirm-lock, monthly archive, backup, Docker Compose deployment.
