"""One-time generator. Builds the CURRENT ExcelGenerator for 2026-06 and captures
(constructor inputs serialized) + (normalized output dump). The parity test rebuilds
ExcelGenerator OFFLINE from these inputs, so the test stays fast/deterministic and
proves the build_grid refactor is byte-safe.

Inputs are sourced from the already-committed, deterministic solver dump
`tests/golden/2026-06_assignments.json` plus the real DataLoader technicians (for
.note/.status). This avoids re-running the multi-minute CP-SAT solver while being
byte-faithful: ExcelGenerator output is fully determined by these inputs.
Re-run only if the scheduler intentionally changes.
    Usage: python tests/golden/gen_excel_parity_fixture.py"""
import json
from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.excel_generator import ExcelGenerator
from tests.golden.xlsx_dump import dump_workbook

YEAR, MONTH, DATA_DIR = 2026, 6, "shift_scheduler/data"


def _int_days(d):
    return {int(k): v for k, v in d.items()}


def main():
    with open("tests/golden/2026-06_assignments.json", encoding="utf-8") as f:
        a = json.load(f)
    technicians = DataLoader(data_dir=DATA_DIR).load_all(f"{YEAR}-{MONTH:02d}")[0]

    day_assignments = _int_days(a["day_assignments"])
    night_assignments = _int_days(a["night_assignments"])
    requests = _int_days(a["requests"])
    on_call_assignments = _int_days(a["on_call_assignments"])

    gen = ExcelGenerator(
        year=YEAR, month=MONTH, technicians=technicians,
        night_assignments=night_assignments,
        day_assignments=day_assignments,
        requests=requests,
        on_call_assignments=on_call_assignments,
        daikyu_counts=a["daikyu_counts"],
        off_counts=a["off_counts"],
        validation_errors=a["validation_errors"],
    )
    dump = dump_workbook(gen.generate_bytes())

    # Serialize ONLY what ExcelGenerator reads off a Staff: id/name/status/note.
    techs = [{"id": t.id, "name": t.name, "status": t.status,
              "note": getattr(t, "note", "") or ""}
             for t in technicians]
    fixture = {
        "year": YEAR, "month": MONTH,
        "technicians": techs,
        "day_assignments": a["day_assignments"],
        "night_assignments": a["night_assignments"],
        "requests": a["requests"],
        "on_call_assignments": a["on_call_assignments"],
        "daikyu_counts": a["daikyu_counts"],
        "off_counts": a["off_counts"],
        "validation_errors": a["validation_errors"],
        "expected_dump": dump,
    }
    with open("tests/golden/2026-06_excel_parity.json", "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1)
    print("wrote tests/golden/2026-06_excel_parity.json")


if __name__ == "__main__":
    main()
