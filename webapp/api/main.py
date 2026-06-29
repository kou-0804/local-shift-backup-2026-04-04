from typing import Any, Dict
from urllib.parse import quote

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, conint

from webapp.api.config import settings
from webapp.api.db import get_db
from webapp.api.jobs import JobStore, run_job
from webapp.api import rosters as roster_ops
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


# --- P2a-2: roster editing backend (freeze / read / edit / undo / redo) ---


@app.post("/jobs/{job_id}/freeze", status_code=201)
def freeze_job(job_id: str, conn=Depends(get_db)):
    job = store.get(job_id)
    if job is None or job.result is None:
        raise HTTPException(status_code=404, detail="result not available")
    from shift_scheduler.src.loaders.data_loader import DataLoader
    technicians = DataLoader(data_dir=settings.data_dir).load_all(
        f"{job.year}-{job.month:02d}")[0]
    rid = roster_ops.freeze_roster(
        conn, job_id=job_id, result=job.result, technicians=technicians,
        data_dir=settings.data_dir, target_holidays=9)
    return {"roster_id": rid}


def _roster_or_404(conn, rid):
    hdr = conn.execute("SELECT id FROM rosters WHERE id=?", (rid,)).fetchone()
    if hdr is None:
        raise HTTPException(status_code=404, detail="roster not found")


@app.get("/rosters/{rid}")
def get_roster(rid: int, conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    grid, d = roster_ops.build_roster_grid(conn, rid)
    # Contract reconciliation (P2d): top-level year/month so the client can build
    # ISO dates for edit payloads.
    return {"version": d["version"], "status": d["status"],
            "year": d["year"], "month": d["month"],
            "grid": grid, "warnings": roster_ops.roster_warnings(d)}


@app.get("/rosters/{rid}/grid")
def get_roster_grid(rid: int, conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    grid, _ = roster_ops.build_roster_grid(conn, rid)
    return grid


@app.post("/rosters/{rid}/edits")
def post_edit(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    # The edit body is a free dict (ops differ in shape); apply_edit validates it.
    # `expected_version` mismatch -> 409 with the current grid for client rebase.
    _roster_or_404(conn, rid)
    try:
        return roster_ops.apply_edit(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)


@app.post("/rosters/{rid}/undo")
def post_undo(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    try:
        return roster_ops.undo(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)


@app.post("/rosters/{rid}/redo")
def post_redo(rid: int, payload: Dict[str, Any], conn=Depends(get_db)):
    _roster_or_404(conn, rid)
    try:
        return roster_ops.redo(conn, rid, payload)
    except roster_ops.ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=exc.grid)
