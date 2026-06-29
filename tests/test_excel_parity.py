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
