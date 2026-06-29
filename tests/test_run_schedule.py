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
