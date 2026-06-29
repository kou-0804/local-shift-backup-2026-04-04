# tests/test_api.py
from fastapi.testclient import TestClient
from webapp.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


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
