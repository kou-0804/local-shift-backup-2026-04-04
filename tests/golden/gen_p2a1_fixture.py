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
    # build_grid is the single source for all live paths (Excel/web/edit), incl.
    # display-only overrides like 矢野(T003) の MR 表記。Derive expected_cells from it
    # (not the legacy _get_assignment_text, which bypasses build_grid's overrides).
    cells_by_sid = {r["staff_id"]: r["cells"] for r in gen.grid["rows"]}
    expected_cells = {
        t.id: {str(d): cells_by_sid.get(t.id, {}).get(d, "") for d in range(1, days + 1)}
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
