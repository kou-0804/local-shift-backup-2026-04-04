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
