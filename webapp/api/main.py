from urllib.parse import quote

from fastapi import FastAPI, BackgroundTasks, HTTPException, Response
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
    # RFC 5987: non-ASCII filenames must be percent-encoded (HTTP headers are latin-1).
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=job.result.workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )
