# Web App P3a — Master Management (SQLite) & Byte-Exact CSV Materialize — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.

**User intent (verbatim, do not dilute):** 「コスト度外視...最高水準で...本番はWindows」 — cost is no object, build to the highest standard, **production runs on Windows**. The whole reason this plan exists is that Windows line-ending/encoding handling can silently corrupt byte-identity; treat the byte-exact gate as non-negotiable.

**Goal:** Move the 8 on-disk master CSVs (`shift_scheduler/data/`) into SQLite as a versioned `master_set`, with full CRUD + validation + a hardcoded-staff-ID safety gate, **without changing one byte of what the solver sees**. Generation still calls `run_schedule(year, month, data_dir=...)`, so P3 must **materialize a `master_set` (+ a selected 予定申請 import) back into a temp directory of CSVs that are byte-identical to the current `shift_scheduler/data/` files**. The keystone is a round-trip golden gate: import current CSVs → materialize → assert every file is byte-identical → assert `run_schedule(data_dir=tmp)` still matches the existing parity golden.

**Architecture:** A new `webapp/api/masters/` package owns master persistence. SQLite gains additive tables (one `master_set` row = a bundle; per-master typed tables carry `master_set_id`; a `master_file_profile` table carries the per-file byte-fidelity descriptor so the serializer can rebuild exact bytes from structured data). `import_dir()` parses the current `data/` CSVs into a `master_set` (the starting point). `materialize()` renders a `master_set` + a `requests_import` back into a temp `data_dir` of byte-identical CSVs by **hand-serializing bytes** (binary writes, per-file BOM/newline/trailing-newline pinned) — never via pandas, which would re-encode and re-normalize newlines. The job worker calls `materialize()` then the existing `run_schedule(data_dir=tmp)`. A FastAPI router exposes per-master CRUD with validation; a safety module enforces the load-bearing IDs before any generation; a separate import-only endpoint ingests 予定申請.

**Tech Stack:** Python 3.13, SQLite (stdlib `sqlite3`, existing `webapp/api/db.py` patterns), FastAPI + Uvicorn (existing), pytest + httpx `TestClient` (existing). No pandas in the materialize path (stdlib `csv` + `io.StringIO` + explicit byte assembly). Determinism preserved: same `master_set` → identical bytes → identical solve (seed=42 / num_workers=1, untouched).

**Scope note (P3a = BACKEND only):** SQLite master schema, import, byte-exact materialize, CRUD REST API + validation, the safety gate + advisory warnings, and the 予定申請 import endpoint. The React master-editor UI is **P3b** (separate plan — see Next). Do not build UI here. Do not touch the solver, the schedulers, or the existing P1/P2 roster/edit code paths except the one-line worker wiring in Task 4.

---

## Reference: the real byte profiles (MEASURED — do not trust the masters map's "utf-8-sig" labels)

The masters map says several files are "utf-8-sig". That describes the **loader's `pd.read_csv(encoding=...)` declaration**, which transparently accepts BOM-or-no-BOM. It is **NOT** the on-disk byte truth. Measured from `shift_scheduler/data/` on 2026-06-29:

| logical_name | filename | BOM? | newline | trailing newline? | loader encoding decl. |
|---|---|---|---|---|---|
| `staff` | 技師マスタ_確定版.csv | **no** | `\n` (LF) | yes | utf-8-sig |
| `skill` | スキルマスタ_確定版.csv | **no** | `\r\n` (CRLF) | yes | utf-8-sig |
| `holiday_targets` | 公休数マスタ_確定版.csv | **no** | `\n` (LF) | yes | utf-8 |
| `location_pb` | 勤務場所マスタ_確定版.csv | **no** | `\r\n` (CRLF) | yes | utf-8-sig |
| `special_rules` | 特殊配置ルール_確定版.csv | **no** | `\n` (LF) | yes | utf-8-sig |
| `training` | 業務拡大マスタ_確定版.csv | **no** | `\n` (LF) | yes | utf-8 |
| `night_quota` | 夜勤回数_確定版.csv | **no** | `\r\n` (CRLF) | yes | utf-8 (skiprows=1) |
| `night_overrides` | 夜勤スキル一覧.csv | **no** | `\r\n` (CRLF) | **no** | (pandas default) |
| `requests` | 予定申請.csv | **YES** | `\r\n` (CRLF) | **no** | utf-8-sig |

**Implications the implementer MUST internalize:**
- Only `予定申請.csv` has a BOM. Writing the other 8 with a BOM (the naive "utf-8-sig" reading of the map) **breaks byte-identity**.
- Line endings are mixed per-file (4 CRLF, 4 LF among masters). You cannot pick one globally.
- Two files (`夜勤スキル一覧.csv`, `予定申請.csv`) have **no** final newline.
- **Windows:** opening in text mode translates `\n`→`\r\n` on write. You MUST write in binary mode (`open(path, 'wb')`) with the newline already embedded in the assembled string, or pin `newline=''` and encode yourself. Pandas `to_csv` will not reproduce these profiles — hand-serialize.
- Capture these profiles **from the real files at import time** (Task 2) into `master_file_profile`; do not hardcode the table above into the serializer. The table is the regression fixture (Task 3 asserts the captured profile matches it), not the source of truth.

Structural quirks the serializer must reproduce (captured into `master_file_profile.format_json`):
- **`勤務場所マスタ`** = two stacked tables: section A (22 location rows) → a separator row `---パワーバランス設定---,,,,,,,,,,,,` → a blank pad row `,,,,,,,,,,,,` → section-B header `場所コード,最低ランク,最低人数,CD上限,D単独禁止,,,,,,,,` → section-B rows, each padded with trailing commas to 13 fields (e.g. `病院MR,A,1,,○,,,,,,,,`). A `場所コード` may appear on multiple section-B rows (additive). Final line is an empty line (trailing newline).
- **`夜勤回数`** = decorative title row `６月夜勤回数,,` → header `名前,7月,` → one row per staff `名前,count,` (trailing empty 3rd column) → footer `合計,93,` and `必要当直者数,93,`. The **column header** (`7月`) is the authoritative month, not the title.
- **`夜勤スキル一覧`** = header `SName,NightShiftMR,NightShiftCardiacCath,NightShiftAngio,` then ~37 empty columns then a stray `2026/1/1` in the last header cell; data rows carry a vestigial free-text qual code in col 5 and trailing empty columns. No final newline.
- **`業務拡大`** = trainee lists containing commas are double-quoted (`"平野裕, 星, 松井, 野口, 中村, 棚町"`); instructor sentinel `ランクA保持者` is literal text. `csv.writer` with `QUOTE_MINIMAL` reproduces the quoting.

---

## File Structure

New package `webapp/api/masters/`:
- Create `webapp/api/masters/__init__.py`
- Create `webapp/api/masters/schema.py` — `MASTER_SCHEMA` DDL string + `init_master_db(conn)`.
- Create `webapp/api/masters/profiles.py` — `FileProfile` dataclass, `capture_profile(path)`, `write_bytes(rows, profile)` (the byte-exact serializer core).
- Create `webapp/api/masters/import_dir.py` — `import_dir(conn, data_dir, name, created_by) -> master_set_id` (parse current CSVs into a `master_set`).
- Create `webapp/api/masters/materialize.py` — `materialize(conn, master_set_id, year, month, request_import_id, dest_dir)` → byte-exact temp `data_dir`.
- Create `webapp/api/masters/crud.py` — per-master list/create/update/delete row functions.
- Create `webapp/api/masters/validation.py` — per-master validators (raise `ValidationError`).
- Create `webapp/api/masters/safety.py` — `LOAD_BEARING_IDS`, `assert_load_bearing_ids(conn, master_set_id)`, advisory warning helpers.
- Create `webapp/api/masters/routes.py` — FastAPI `APIRouter` mounting CRUD + 予定申請 import; included from `webapp/api/main.py`.
- Create `webapp/api/requests_import.py` — 予定申請 upload/validate/preview/store (import-only).
- Modify `webapp/api/db.py` — call `init_master_db(conn)` inside `init_db()` (additive).
- Modify `webapp/api/config.py` — add `default_master_set_id` resolution + temp-dir base.
- Modify `webapp/api/jobs.py` / `webapp/api/main.py` — wire generation through `materialize()` (Task 4).

Tests (all under `tests/`):
- `tests/test_master_schema.py`
- `tests/test_master_profiles.py`
- `tests/test_master_import.py`
- `tests/test_master_materialize_roundtrip.py` ← **keystone (byte-identical)**
- `tests/test_master_generation_parity.py` ← `@pytest.mark.slow`
- `tests/test_master_crud.py`
- `tests/test_master_validation.py`
- `tests/test_safety_gate.py`
- `tests/test_requests_import.py`

All commands assume repo root `"/Users/kohei/Desktop/local-shift ver1"` is CWD and the venv is active (`source .venv/bin/activate`). Use `python -m pytest -p no:cacheprovider` for clean runs.

**Order rationale:** Schema (1) → Import (2) → **Materialize byte-exact round-trip gate (3, keystone)** → Generation parity through materialize (4) → CRUD + validation (5) → Safety gate + warnings (6) → 予定申請 import (7). The byte-exact gate is established before any CRUD so every later edit is validated against an immovable "these bytes still parse to the same solve" backstop.

---

## Task 1: SQLite master schema (`master_set` + typed master tables + file profile)

**Files:** Create `webapp/api/masters/schema.py`; Modify `webapp/api/db.py`; Test `tests/test_master_schema.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_master_schema.py
import sqlite3
from webapp.api.masters.schema import init_master_db, MASTER_TABLES


def _mem():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_init_master_db_creates_all_tables():
    conn = _mem()
    init_master_db(conn)
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert MASTER_TABLES <= names


def test_init_master_db_is_idempotent():
    conn = _mem()
    init_master_db(conn)
    init_master_db(conn)  # must not raise (IF NOT EXISTS)


def test_master_set_parent_fk_and_iso_created_at():
    conn = _mem()
    init_master_db(conn)
    conn.execute(
        "INSERT INTO master_set(name,note,created_at,created_by,parent_set_id)"
        " VALUES('現行','seed','2026-06-29T00:00:00',?,NULL)", ("kohei",))
    row = conn.execute("SELECT * FROM master_set").fetchone()
    assert row["parent_set_id"] is None
    assert row["created_at"] == "2026-06-29T00:00:00"  # ISO 8601


def test_file_profile_columns_present():
    conn = _mem()
    init_master_db(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(master_file_profile)")}
    assert {"master_set_id", "logical_name", "filename", "has_bom",
            "newline", "trailing_newline", "header_text", "format_json"} <= cols
```

- [ ] **Step 2: Run, verify failure** — `python -m pytest tests/test_master_schema.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `webapp/api/masters/schema.py`.

Define `MASTER_SCHEMA` (one `CREATE TABLE IF NOT EXISTS` per table) and `MASTER_TABLES` (the set of table names). Tables (synthetic English snake_case columns; Japanese CSV headers/values are preserved as data, not column names). All `created_at` are ISO-8601 TEXT. Every per-master table carries `master_set_id INTEGER NOT NULL REFERENCES master_set(id) ON DELETE CASCADE` and a `row_order INTEGER NOT NULL` (preserves CSV line order — **load-bearing**: 技師マスタ row order drives Excel row order; section-B additive rows must round-trip in order).

```
master_set(id PK, name, note, created_at, created_by, parent_set_id REFERENCES master_set(id))

ms_staff(id PK, master_set_id FK, row_order, tech_id, name, gender, experience_years,
         night_ok, status, note, oncall_ok)            -- night_ok/oncall_ok stored as '○'/'×' text
ms_skill_row(id PK, master_set_id FK, row_order, tech_id, name)
ms_skill_cell(id PK, master_set_id FK, tech_id, loc_code, rank)   -- long form; one cell per (tech,loc)
ms_location(id PK, master_set_id FK, row_order, loc_code, loc_name, category,
            mon,tue,wed,thu,fri,sat,sun, gender_constraint, display_order, active)
ms_power_balance(id PK, master_set_id FK, row_order, loc_code, min_rank, min_count, cd_cap, d_solo_ban)
ms_special_rule(id PK, master_set_id FK, row_order, rule_id, loc_code, weekday, week,
                required_count, rank_cond, rank_count, source_loc, source_rank, note)
ms_training(id PK, master_set_id FK, row_order, modality,
            instructor_text, trainee_text, display_name,     -- raw text = byte-exact source of truth
            instructor_ids_json, trainee_ids_json, rank_a_only)  -- resolved, for CRUD UX
ms_night_quota(id PK, master_set_id FK, row_order, year_month, tech_id, name, count)
ms_night_override(id PK, master_set_id FK, row_order, sname, tech_id,
                  night_mr, night_cath, night_angio, qual_code)  -- tri-state stored as 'TRUE'/'FALSE'/NULL
ms_holiday_target(id PK, master_set_id FK, row_order, year_month, holiday_count)

master_file_profile(id PK, master_set_id FK, logical_name, filename,
                    has_bom INT, newline TEXT, trailing_newline INT, header_text TEXT, format_json TEXT,
                    UNIQUE(master_set_id, logical_name))

requests_import(id PK, year_month, source_filename, imported_at, imported_by,
                raw_blob BLOB, has_bom INT, newline TEXT, trailing_newline INT)
request_row(id PK, import_id FK REFERENCES requests_import(id) ON DELETE CASCADE,
            tech_id_resolved, date, symbol, raw_rsname, resolve_status)
```

`MASTER_TABLES = {"master_set","ms_staff","ms_skill_row","ms_skill_cell","ms_location","ms_power_balance","ms_special_rule","ms_training","ms_night_quota","ms_night_override","ms_holiday_target","master_file_profile","requests_import","request_row"}`.

`init_master_db(conn)` runs `conn.executescript(MASTER_SCHEMA); conn.commit()`.

- [ ] **Step 4:** In `webapp/api/db.py`, import and call `init_master_db(conn)` from inside `init_db(conn)` (after the existing `executescript(SCHEMA)`), so every connection (incl. tests via `get_db`) gets the master tables. Additive — does not touch existing roster tables.

- [ ] **Step 5: Run** `python -m pytest tests/test_master_schema.py tests/test_db.py -v` → all pass (existing `test_db.py` must stay green — proves additive).

- [ ] **Step 6: Commit** — `feat(p3-master): add SQLite master_set schema + file-profile table`

---

## Task 2: Import current `data/` CSVs → a `master_set` (+ capture byte profiles)

**Files:** Create `webapp/api/masters/profiles.py`, `webapp/api/masters/import_dir.py`; Test `tests/test_master_profiles.py`, `tests/test_master_import.py`.

This establishes the **starting point** master_set and, crucially, captures each file's byte profile so the serializer (Task 3) can rebuild exact bytes.

- [ ] **Step 1: Profile-capture test (write first)**

```python
# tests/test_master_profiles.py
from webapp.api.masters.profiles import capture_profile

DATA = "shift_scheduler/data"

EXPECTED = {  # the MEASURED reference table — regression guard
    "技師マスタ_確定版.csv":   (False, "\n",   True),
    "スキルマスタ_確定版.csv":  (False, "\r\n", True),
    "公休数マスタ_確定版.csv":  (False, "\n",   True),
    "勤務場所マスタ_確定版.csv": (False, "\r\n", True),
    "特殊配置ルール_確定版.csv": (False, "\n",   True),
    "業務拡大マスタ_確定版.csv": (False, "\n",   True),
    "夜勤回数_確定版.csv":     (False, "\r\n", True),
    "夜勤スキル一覧.csv":      (False, "\r\n", False),
    "予定申請.csv":           (True,  "\r\n", False),
}


def test_capture_profile_matches_measured_truth():
    import os
    for fn, (bom, nl, trail) in EXPECTED.items():
        p = capture_profile(os.path.join(DATA, fn))
        assert (p.has_bom, p.newline, p.trailing_newline) == (bom, nl, trail), fn
```

- [ ] **Step 2: Run, verify failure** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `profiles.py`.**

```python
# webapp/api/masters/profiles.py
import io, csv
from dataclasses import dataclass

BOM = b"\xef\xbb\xbf"


@dataclass
class FileProfile:
    logical_name: str
    filename: str
    has_bom: bool
    newline: str            # "\n" or "\r\n"
    trailing_newline: bool
    header_text: str        # exact first physical line (decoded, sans BOM, sans newline)
    format_json: dict       # per-file structural extras (separator rows, title, stray cols, ...)


def capture_profile(path, *, logical_name="", format_json=None) -> FileProfile:
    raw = open(path, "rb").read()
    has_bom = raw.startswith(BOM)
    body = raw[len(BOM):] if has_bom else raw
    newline = "\r\n" if b"\r\n" in body else "\n"
    trailing_newline = body.endswith(b"\n")
    first = body.split(b"\n", 1)[0].decode("utf-8").rstrip("\r")
    import os
    return FileProfile(logical_name, os.path.basename(path), has_bom, newline,
                       trailing_newline, first, format_json or {})


def write_bytes(rows, profile: FileProfile) -> bytes:
    """rows: list[list[str]] -> exact CSV bytes per the profile.
    Hand-serialized: stdlib csv for quoting fidelity, then explicit newline/BOM/trailing control.
    NEVER use pandas here (it re-encodes and re-normalizes newlines)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator=profile.newline, quoting=csv.QUOTE_MINIMAL)
    for r in rows:
        w.writerow(r)
    text = buf.getvalue()
    if not profile.trailing_newline and text.endswith(profile.newline):
        text = text[: -len(profile.newline)]
    data = text.encode("utf-8")
    return (BOM + data) if profile.has_bom else data
```

> Note: `csv.writer` with `QUOTE_MINIMAL` reproduces the 業務拡大 trainee quoting and the pad-comma empty fields. The two no-trailing-newline files are handled by stripping the final terminator. Round-trip parity (Task 3) is the proof this is correct; if any file mismatches, adjust `write_bytes` (e.g. quoting edge cases) — do NOT special-case bytes by hand.

- [ ] **Step 4: Import test (write first)**

```python
# tests/test_master_import.py
import sqlite3
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir

DATA = "shift_scheduler/data"


def _mem():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); init_master_db(c); return c


def test_import_dir_creates_master_set_and_rows():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="kohei")
    assert msid == 1
    n_staff = c.execute("SELECT COUNT(*) n FROM ms_staff WHERE master_set_id=?", (msid,)).fetchone()["n"]
    assert n_staff == 72                         # 72 data rows (67 在籍 + 5 退職)
    # load-bearing IDs all present
    ids = {r["tech_id"] for r in c.execute("SELECT tech_id FROM ms_staff WHERE master_set_id=?", (msid,))}
    assert {"T001","T013","T025","T072","T002","T022","T006","T023"} <= ids
    # all 9 file profiles captured
    profs = c.execute("SELECT COUNT(*) n FROM master_file_profile WHERE master_set_id=?", (msid,)).fetchone()["n"]
    assert profs == 9


def test_import_dir_preserves_row_order():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="kohei")
    first = c.execute("SELECT tech_id FROM ms_staff WHERE master_set_id=? ORDER BY row_order LIMIT 1",
                      (msid,)).fetchone()["tech_id"]
    assert first == "T001"  # CSV order is row order, not numeric-id order


def test_import_dir_section_b_additive_rows():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="kohei")
    n = c.execute("SELECT COUNT(*) n FROM ms_power_balance WHERE master_set_id=? AND loc_code='病院MR'",
                  (msid,)).fetchone()["n"]
    assert n == 2  # 病院MR appears twice (rank A min1, rank B min2)
```

- [ ] **Step 5: Implement `import_dir.py`.** One parse function per master; reuse the existing loaders **only where convenient for row content**, but capture row order and the structural extras directly from the file lines (the loaders drop ordering/garbage). For each master:
  - `staff`: read lines, store each row's 8 fields in `ms_staff` with `row_order`; capture profile.
  - `skill`: store `ms_skill_row` (tech_id, name) + `ms_skill_cell` (one per location code, in column order); `format_json={"columns": [...22 codes...], "meta_cols": ["技師ID","氏名"]}` so column order round-trips.
  - `location_pb`: split on `---パワーバランス設定---`; section A → `ms_location`, section B → `ms_power_balance`; `format_json` records the separator row text, blank pad row, section-B header text, and field-width (13) for padding.
  - `special_rules`: store SR-* rows AND keep legend/comment lines verbatim in `format_json["tail_lines"]` so they round-trip (loader skips them, but bytes must survive).
  - `training`: store raw `instructor_text`/`trainee_text` verbatim (byte source of truth) + resolved IDs + `rank_a_only` flag.
  - `night_quota`: `format_json={"title": "６月夜勤回数", "month_header": "7月", "trailing_col": True, "footer": ["合計","必要当直者数"]}`; store per-staff rows; footer 合計 is recomputed at materialize (= sum), 必要当直者数 stored as-is.
  - `night_override`: store 4 honored fields + qual_code; `format_json` records the ~37 trailing empty columns and the stray `2026/1/1` header token so the wide header/rows round-trip.
  - `holiday_targets`: 12 rows (年月, 公休数).
  - For each file call `capture_profile(path, logical_name=..., format_json=...)` and insert into `master_file_profile`.

  Wrap the whole import in one transaction; `created_at = datetime.now().isoformat(timespec="seconds")`.

- [ ] **Step 6: Run** `python -m pytest tests/test_master_profiles.py tests/test_master_import.py -v` → pass.

- [ ] **Step 7: Commit** — `feat(p3-master): import data/ CSVs into a master_set + capture byte profiles`

---

## Task 3 (KEYSTONE): Byte-exact materialize + round-trip golden gate

**Files:** Create `webapp/api/masters/materialize.py`; Test `tests/test_master_materialize_roundtrip.py`.

This is the most important test in P3. If it passes, every later CRUD edit is provably re-serializable to bytes the solver already accepts.

- [ ] **Step 1: Write the failing keystone test**

```python
# tests/test_master_materialize_roundtrip.py
import os, sqlite3, tempfile
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.materialize import materialize_masters

DATA = "shift_scheduler/data"
MASTER_FILES = [
    "技師マスタ_確定版.csv", "スキルマスタ_確定版.csv", "公休数マスタ_確定版.csv",
    "勤務場所マスタ_確定版.csv", "特殊配置ルール_確定版.csv", "業務拡大マスタ_確定版.csv",
    "夜勤回数_確定版.csv", "夜勤スキル一覧.csv",
]


def _mem():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); init_master_db(c); return c


def test_materialize_is_byte_identical_to_source():
    c = _mem()
    msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(c, msid, dest_dir=tmp)
        for fn in MASTER_FILES:
            got = open(os.path.join(tmp, fn), "rb").read()
            want = open(os.path.join(DATA, fn), "rb").read()
            assert got == want, f"BYTE MISMATCH in {fn}: {len(got)} vs {len(want)} bytes"


def test_materialize_is_deterministic():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        materialize_masters(c, msid, dest_dir=a)
        materialize_masters(c, msid, dest_dir=b)
        for fn in MASTER_FILES:
            assert open(os.path.join(a, fn), "rb").read() == open(os.path.join(b, fn), "rb").read()
```

> Debugging aid for the implementer: when a file mismatches, diff line-by-line on the raw bytes (`got.split(profile.newline.encode())` vs source) — the failure is almost always (a) wrong newline, (b) an unwanted BOM, (c) a missing/extra trailing newline, or (d) a dropped pad-comma / quoting difference. Fix the serializer or the captured `format_json`, never the assertion.

- [ ] **Step 2: Run, verify failure** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `materialize.py`.** `materialize_masters(conn, master_set_id, *, dest_dir)`:
  - For each logical_name, load its `FileProfile` from `master_file_profile`, load the structured rows (ordered by `row_order`), render `rows: list[list[str]]` reproducing the exact field layout (including pad commas / title / separator / footer per `format_json`), call `profiles.write_bytes(rows, profile)`, and write **binary**:
    ```python
    with open(os.path.join(dest_dir, profile.filename), "wb") as f:
        f.write(write_bytes(rows, profile))
    ```
  - **Windows pin:** binary mode + newline pre-embedded means the OS never translates `\n`→`\r\n`. Do not use `csv.writer` on a file handle (that path is OS-newline-sensitive); always serialize to bytes first, write `'wb'`.
  - `night_quota`: recompute 合計 = sum(counts); emit title row, header `名前,<month_header>,`, per-staff `name,count,`, then `合計,<sum>,` and `必要当直者数,<stored>,`.
  - `skill`: emit header = meta_cols + ordered location columns; each row = tech_id, name, then ranks in column order (NONE → `-` only if the source cell was `-`; preserve the literal stored cell).
  - `location_pb`: emit section A rows, separator row, blank pad row, section-B header, section-B rows (padded to 13 fields), final empty line via trailing newline.
  - `special_rules`: emit SR rows then the verbatim `tail_lines` (legend) from `format_json`.
  - `night_override`: emit the wide header (incl. stray `2026/1/1`) and rows with the trailing empty columns, no final newline.

- [ ] **Step 4: Run the keystone** `python -m pytest tests/test_master_materialize_roundtrip.py -v` → **all 9 files byte-identical, deterministic**. Iterate on the serializer until green. Do not proceed past this task until it passes.

- [ ] **Step 5: Commit** — `feat(p3-master): byte-exact materialize + round-trip golden gate (keystone)`

---

## Task 4: Wire generation through materialize (+ parity golden through the temp dir)

**Files:** Modify `webapp/api/jobs.py`, `webapp/api/main.py`, `webapp/api/config.py`, Create the 予定申請-aware `materialize_data_dir`; Test `tests/test_master_generation_parity.py`.

- [ ] **Step 1: Write the slow parity test (write first)**

```python
# tests/test_master_generation_parity.py
import json, os, sqlite3, tempfile, pytest
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.materialize import materialize_masters
from main import run_schedule

DATA = "shift_scheduler/data"
GOLDEN = "tests/golden/2026-06_assignments.json"


def _mem():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); init_master_db(c); return c


@pytest.mark.slow
def test_run_schedule_via_materialized_dir_matches_golden():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="t")
    with tempfile.TemporaryDirectory() as tmp:
        materialize_masters(c, msid, dest_dir=tmp)
        # request file: copy the current 予定申請.csv in as the month-suffixed name
        import shutil
        shutil.copyfile(os.path.join(DATA, "予定申請.csv"),
                        os.path.join(tmp, "予定申請_202606.csv"))
        actual = run_schedule(2026, 6, data_dir=tmp).as_dict()
    expected = json.load(open(GOLDEN, encoding="utf-8"))
    actual = json.loads(json.dumps(actual, ensure_ascii=False, sort_keys=True))
    expected = json.loads(json.dumps(expected, ensure_ascii=False, sort_keys=True))
    assert actual == expected
```

- [ ] **Step 2: Run, verify failure** (or xfail until wiring exists) → assertion/import failure.

- [ ] **Step 3: Implement** a top-level `materialize_data_dir(conn, master_set_id, year, month, request_import_id, dest_dir)` in `materialize.py` that calls `materialize_masters` **and** writes the selected `requests_import.raw_blob` to `予定申請_{year}{month:02d}.csv` (byte-verbatim from the stored blob — see Task 7). The month-suffixed name guarantees `request_loader` picks it over any generic `予定申請.csv` fallback (no stale-month bug).

- [ ] **Step 4: Wire the worker.** In `webapp/api/jobs.py` / `main.py`, before calling `run_schedule`, create a `tempfile.mkdtemp()` (under `config.temp_base`), call `materialize_data_dir(...)` with the job's `master_set_id` (default = the seeded "現行" set; resolve via `config.default_master_set_id`) and the month's `request_import_id`, then `run_schedule(year, month, data_dir=tmp)`. Clean up the temp dir in a `finally`. Keep the existing `_solve_lock` serialization (determinism). Generation must call the safety gate first (Task 6) — add that call here once Task 6 lands.

- [ ] **Step 5: Run** `python -m pytest tests/test_master_generation_parity.py -v -m slow` and the existing `tests/test_parity_golden.py` → both green (proves materialized dir is solver-equivalent to the real `data/`).

- [ ] **Step 6: Commit** — `feat(p3-master): generate via materialized master_set (parity golden through temp dir)`

---

## Task 5: Per-master CRUD REST API + validation

**Files:** Create `webapp/api/masters/crud.py`, `webapp/api/masters/validation.py`, `webapp/api/masters/routes.py`; Modify `webapp/api/main.py` (include router); Test `tests/test_master_crud.py`, `tests/test_master_validation.py`.

CRUD targets the 7 editable masters (staff, skill, location, power_balance, special_rules, training, night_quota, night_overrides, holiday_targets). 予定申請 is import-only (Task 7).

- [ ] **Step 1: Validation tests (write first)** — one assertion per rule from spec §9 / masters map:

```python
# tests/test_master_validation.py
import pytest
from webapp.api.masters import validation as v

def test_tech_id_must_be_tnnn():
    with pytest.raises(v.ValidationError): v.validate_staff_row({"tech_id": "X1", "name": "a　b",
        "gender": "男", "experience_years": 3, "night_ok": "○", "status": "在籍", "oncall_ok": "○"})

def test_tech_id_unique_within_set(monkeypatch):
    with pytest.raises(v.ValidationError):
        v.validate_tech_id_unique(existing={"T001"}, tech_id="T001")

def test_skill_rank_domain():
    for r in ["A","B","C","D","-"]: v.validate_skill_rank(r)
    with pytest.raises(v.ValidationError): v.validate_skill_rank("E")

def test_holiday_year_month_must_be_zero_padded():
    v.validate_year_month("2026/04")
    with pytest.raises(v.ValidationError): v.validate_year_month("2026/4")   # the #1 silent footgun

def test_full_width_space_name_join_integrity():
    with pytest.raises(v.ValidationError):
        v.validate_name_join("石川 和弥", known_names={"石川　和弥"})  # half-width space won't join

def test_power_balance_code_must_reference_location():
    with pytest.raises(v.ValidationError):
        v.validate_pb_location_ref("存在しない", location_codes={"病院MR","CT"})

def test_night_quota_total_must_equal_sum():
    with pytest.raises(v.ValidationError):
        v.validate_night_quota_total(rows_sum=92, declared_total=93)

def test_training_names_must_resolve():
    with pytest.raises(v.ValidationError):
        v.validate_training_names(["幽霊"], staff_names={"小川　龍史"})
```

- [ ] **Step 2: Run, verify failure** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `validation.py`** — `ValidationError(Exception)` carrying a `field` + a clear JP message. Rules: tech_id `^T\d{3}$` + unique; gender ∈ {男,女}; experience_years int ≥ 0; night_ok/oncall_ok ∈ {○,×}; status ∈ {在籍,退職}; skill rank ∈ {A,B,C,D,-}; year_month `^\d{4}/(0[1-9]|1[0-2])$` (rejects `2026/4`); 公休数 int sane bounds; full-width-space name must exist in the cross-file name set (技師マスタ ↔ 夜勤回数 ↔ requests); section-B 場所コード references an existing section-A location code; 夜勤回数 合計 == sum(counts); training instructor/trainee names resolve to staff (or the explicit `rank_a_only` toggle); special_rule weekday ∈ {月..日,水金,-}, week ∈ {1..5,-}, counts int.

- [ ] **Step 4: CRUD tests (write first)** — through the FastAPI `TestClient`, exercise list/create/update/delete for staff and skill, asserting validation 422s:

```python
# tests/test_master_crud.py
from fastapi.testclient import TestClient
from webapp.api.main import app
# fixtures: override get_db with an in-memory conn seeded by import_dir (see tests/test_api.py pattern)

def test_list_staff_returns_imported_rows(client):
    r = client.get("/masters/1/staff"); assert r.status_code == 200
    assert len(r.json()) == 72

def test_create_staff_rejects_bad_id(client):
    r = client.post("/masters/1/staff", json={"tech_id":"X1","name":"試 験",...})
    assert r.status_code == 422

def test_update_skill_cell_constrains_rank(client):
    r = client.put("/masters/1/skill/T001", json={"病院MR":"E"}); assert r.status_code == 422

def test_delete_then_list(client):
    assert client.delete("/masters/1/holiday_targets/2027-03").status_code == 200
```

- [ ] **Step 5: Implement `crud.py` + `routes.py`.** `crud.py`: pure functions `(conn, master_set_id, ...)` → list/insert/update/delete that call `validation` first, then mutate the typed tables (re-deriving `row_order` on insert; preserving on update). `routes.py`: an `APIRouter(prefix="/masters")` with `GET/POST/PUT/DELETE /{master_set_id}/{master}` and `/{master_set_id}/{master}/{key}`. Editing a master_set should be done on a **copy** (`POST /masters/{id}/clone` → new `master_set` with `parent_set_id`) so the seeded "現行" stays pristine; CRUD then targets the clone. Include the router from `webapp/api/main.py` via `app.include_router(masters_router)`.

- [ ] **Step 6: Round-trip safety re-check** — add one test asserting that after a no-op clone (clone then materialize) the bytes are still identical to source (clone must deep-copy rows + profiles faithfully).

- [ ] **Step 7: Run** `python -m pytest tests/test_master_validation.py tests/test_master_crud.py -v` → pass.

- [ ] **Step 8: Commit** — `feat(p3-master): per-master CRUD REST API + validation`

---

## Task 6: Hardcoded-staff-ID SAFETY GATE + advisory warnings

**Files:** Create `webapp/api/masters/safety.py`; Modify worker (Task 4 call site) + `routes.py`; Test `tests/test_safety_gate.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_safety_gate.py
import sqlite3, pytest
from webapp.api.masters.schema import init_master_db
from webapp.api.masters.import_dir import import_dir
from webapp.api.masters.safety import (
    LOAD_BEARING_IDS, assert_load_bearing_ids, SafetyError,
    night_eligibility_warnings, special_rule_warnings)

DATA = "shift_scheduler/data"

def _mem():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); init_master_db(c); return c

def test_load_bearing_ids_constant_is_exact():
    assert LOAD_BEARING_IDS == ["T001","T013","T025","T072","T002","T022","T006","T023"]

def test_gate_passes_on_intact_master_set():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="t")
    assert_load_bearing_ids(c, msid)  # must not raise

def test_gate_fails_with_specific_id_when_missing():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="t")
    c.execute("DELETE FROM ms_staff WHERE master_set_id=? AND tech_id='T072'", (msid,))
    with pytest.raises(SafetyError) as e:
        assert_load_bearing_ids(c, msid)
    assert "T072" in str(e.value)      # names the specific missing id, not a generic failure

def test_night_eligibility_warning_on_skill_downgrade():
    c = _mem(); msid = import_dir(c, DATA, name="現行", created_by="t")
    warns = night_eligibility_warnings(c, msid, tech_id="T001", loc_code="病院MR",
                                       old_rank="A", new_rank="C")
    assert warns and "夜勤" in warns[0]

def test_special_rule_warning_on_unenforced_string_condition():
    warns = special_rule_warnings(rank_cond="D同士禁止")
    assert warns and ("未適用" in warns[0] or "未実装" in warns[0])
```

- [ ] **Step 2: Run, verify failure** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `safety.py`.**
  - `LOAD_BEARING_IDS = ["T001","T013","T025","T072","T002","T022","T006","T023"]` (spec §3.5-1: T001 病CT専従/連勤免除, T013+T025 月6回ク相互排他, T072 館山専任 + backups T006/T022/T023, T002 第4火曜PET, T022 月曜DX). Add a comment pointing back to §3.5 so future editors know these are CP-SAT `model.Add` floors that silently no-op if the ID is renamed.
  - `assert_load_bearing_ids(conn, master_set_id)` — query `ms_staff` for the set; if any missing, raise `SafetyError(f"生成不可: コード固定の技師ID {missing} が技師マスタに存在しません。... §3.5 参照")` listing **every** missing id. Reusable; called by the worker (Task 4) before `run_schedule` and exposed at `GET /masters/{id}/safety-check` returning `{ok, missing}`.
  - `night_eligibility_warnings(...)` — if `loc_code ∈ {病院MR,CLMR,ア,心,HB}` and the edit crosses the ≥B threshold (B/A → C/D/- or vice versa), return a JP warning that night eligibility (MR/Cath/Angio/HB) is affected (matches `data_loader.py:33-47` derivation).
  - `special_rule_warnings(rank_cond)` — if `rank_cond ∈ {D同士禁止, CD上限, CD単独禁止}`, return a JP warning that the condition is **documented but currently parsed to NONE and NOT enforced** by the scheduler (dead branch — spec §3.4 / map). These are advisory (non-blocking); CRUD returns them in the response body.

- [ ] **Step 4: Wire the gate** into the Task-4 worker path (raise → job fails with a clear error, never a silent bad solve) and call the warning helpers from the relevant `crud.py` update paths (attach to the JSON response).

- [ ] **Step 5: Run** `python -m pytest tests/test_safety_gate.py -v` → pass.

- [ ] **Step 6: Commit** — `feat(p3-master): load-bearing-ID safety gate + night/special-rule advisory warnings`

---

## Task 7: 予定申請 (Power Apps) import endpoint — import-only

**Files:** Create `webapp/api/requests_import.py`; Modify `routes.py`; Test `tests/test_requests_import.py`.

NOT CRUD. Upload → validate (BOM, skip `Sample Data`/blank rows) → preview (report unresolved RSName) → store per-month (raw bytes BLOB → materialized as `予定申請_YYYYMM.csv`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_requests_import.py
import sqlite3
from webapp.api.masters.schema import init_master_db
from webapp.api.requests_import import preview_requests, store_requests

DATA = "shift_scheduler/data"

def _mem():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); init_master_db(c); return c

def test_preview_skips_sample_and_blank_rows():
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    name_to_id = {"矢野　昌男": "T003"}  # minimal; real test uses imported staff
    pv = preview_requests(raw, name_to_id)
    assert pv["row_count"] > 0
    assert all("Sample Data" not in r["raw_rsname"] for r in pv["rows"])

def test_preview_reports_unresolved_rsname():
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    pv = preview_requests(raw, name_to_id={})       # nothing resolves by name
    assert pv["unresolved"]                          # surfaced, not silently dropped

def test_store_keeps_raw_bytes_for_byte_exact_materialize():
    c = _mem()
    raw = open(f"{DATA}/予定申請.csv", "rb").read()
    imp_id = store_requests(c, year=2026, month=6, raw=raw,
                            source_filename="予定申請.csv", imported_by="t", name_to_id={})
    stored = c.execute("SELECT raw_blob FROM requests_import WHERE id=?", (imp_id,)).fetchone()["raw_blob"]
    assert bytes(stored) == raw                      # verbatim → 予定申請_202606.csv will be byte-exact
```

- [ ] **Step 2: Run, verify failure** → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `requests_import.py`.**
  - `preview_requests(raw, name_to_id)` — decode with BOM tolerance (`utf-8-sig`), auto-detect header within first 5 lines (`HolidaySymbol`/`日付`), skip rows missing PPPDate/HolidaySymbol/RSName, skip `Sample Data`, resolve RSName two-stage (strip leading digits → name match; fallback `NN`→`T0NN`) exactly like `request_loader.py`, and return `{row_count, rows:[{date,symbol,raw_rsname,tech_id_resolved,resolve_status}], unresolved:[...]}`. Include a HolidaySymbol legend (holiday vs forced-work vs 夜希 vs 17休/17業) for the UI.
  - `store_requests(conn, year, month, raw, source_filename, imported_by, name_to_id)` — store **raw bytes verbatim** in `requests_import.raw_blob` (this is the byte-exact source for materialize; import-only so a raw BLOB is correct, not a shortcut) + `request_row` rows from the preview; `imported_at = isoformat`. Capturing `has_bom/newline/trailing_newline` from `raw` is optional since the blob is verbatim, but store them for diagnostics.
  - Route: `POST /masters/requests/preview` (multipart upload → preview JSON) and `POST /masters/requests/{year}/{month}` (commit → import_id). `materialize_data_dir` (Task 4) writes the blob to `予定申請_{year}{month:02d}.csv`.

- [ ] **Step 4: Run** `python -m pytest tests/test_requests_import.py -v` → pass.

- [ ] **Step 5: Commit** — `feat(p3-master): 予定申請 import endpoint (upload/validate/preview/store, month-suffixed)`

---

## Final verification

- [ ] Run the full suite: `python -m pytest -q` (and `python -m pytest -q -m slow` for the parity golds).
- [ ] Confirm the keystone (`tests/test_master_materialize_roundtrip.py`) and both parity golds (`tests/test_parity_golden.py`, `tests/test_master_generation_parity.py`) are green.
- [ ] Confirm existing P1/P2 tests (`tests/test_db.py`, `tests/test_api.py`, roster/edit tests) are still green — P3 is additive.

---

## Self-Review

**Spec coverage (§9 / §3.4 / §3.5 / §5):**
- §5 data model → master_set + per-master typed tables + requests_import/request_row (Task 1). ✅ Forward-compatible with `rosters.master_set_id` (already nullable in `db.py`); Task 4 sets it on new jobs.
- §3.4 eight masters → all 8 imported + materialized byte-exact, incl. the 勤務場所 two-table structure, 夜勤回数 title+footer, 夜勤スキル一覧 stray columns (Tasks 2–3). ✅
- §9 CRUD + validation → Task 5 (tech_id Tnnn+unique, skill ranks domain, 公休数 zero-padded YYYY/MM, full-width-space join, section-B location ref, 夜勤回数 total==sum, training name resolution). ✅
- §9 safety gate → Task 6 (`LOAD_BEARING_IDS`, specific-id failure) + advisory warnings (night ≥B, unenforced D同士禁止/CD上限/CD単独禁止). ✅
- §9 予定申請 import-only → Task 7 (BOM, skip Sample Data/blank, unresolved report, month-suffixed). ✅
- §3.5 hardcoded logic stays in code (not editable) but is **guarded** by the safety gate so re-numbering fails loudly. ✅

**Placeholder scan:** No `...` left in shipped code — the `...` in test bodies (`{"tech_id":"X1",...}`) are illustrative; the implementer fills concrete fixtures (follow the `tests/test_api.py` get_db-override pattern). All function bodies are specified.

**Type consistency:** SQLite stores symbols as text (`○`/`×`, `TRUE`/`FALSE`/NULL tri-state) — never coerced to bool in storage, so materialize round-trips the literal token. `row_order INTEGER` preserves CSV order. `created_at`/`imported_at` are ISO-8601 TEXT. `materialize` deals in `list[list[str]]` → `bytes`; no pandas in the write path.

**Determinism:** Same master_set → identical bytes (`test_materialize_is_deterministic`) → identical solve (seed=42/num_workers=1 untouched). Row ordering is explicit (`ORDER BY row_order`); column ordering comes from the captured `format_json["columns"]`. Temp dirs are per-job and cleaned up.

**Windows byte-identity (the user's 本番はWindows):** Per-file BOM/newline/trailing-newline are captured from the real files and reproduced via **binary writes** with the newline pre-embedded — the OS never re-translates. The measured profile table is a regression fixture (`test_capture_profile_matches_measured_truth`). The keystone gate runs on macOS (dev) and must run identically in CI/Windows.

---

## Next (out of scope for P3a)

- **P3b — React master-editor UI:** flat grids (staff, holiday_targets), constrained-dropdown skill grid {A,B,C,D,-}, two-sub-editor 勤務場所 form, structured 特殊配置ルール form (model 水金 as Wed+Fri, surface the unenforced-string-condition warning), 業務拡大 multi-select pickers + "ランクA保持者" toggle, 夜勤回数 month-picker numeric grid, 夜勤スキル一覧 tri-state grid, 予定申請 upload/preview screen. Backed entirely by the Task-5/Task-7 endpoints. Add clone-before-edit UX and the safety-check banner.
- **Then P5 — auth / confirm-lock / monthly archive** (spec §10): role gating (admin/editor/viewer) on the CRUD + import endpoints, confirm→archive, daily backup of SQLite + archives.
- **Then Windows deployment** (spec §13): Docker Compose (web/api/worker/db), confirm the byte-exact gate runs green in the Windows container, fixed-host/LAN-only firewall, backup media.
