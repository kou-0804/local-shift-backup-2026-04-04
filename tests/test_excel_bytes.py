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
