from typing import Any, Dict
from urllib.parse import quote

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, conint

from webapp.api.config import settings
from webapp.api.db import get_db
from webapp.api.jobs import JobStore, run_job_materialized
from webapp.api import rosters as roster_ops
from webapp.api.masters.routes import router as masters_router, sets_router as master_sets_router
from shift_scheduler.src.excel_directiona import render_directiona
from main import run_schedule

app = FastAPI(title="勤務表 Web API", version="0.1.0")
store = JobStore()
RUNNER = run_schedule  # indirection so tests can monkeypatch a fast fake
app.include_router(masters_router)
app.include_router(master_sets_router)


class JobRequest(BaseModel):
    year: conint(ge=2000, le=2100)
    month: conint(ge=1, le=12)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=201)
def create_job(req: JobRequest, background: BackgroundTasks):
    job = store.create(req.year, req.month)
    # P3: generation runs against a temp data_dir materialized from the default
    # master_set (falls back to settings.data_dir when no master_set is seeded).
    background.add_task(run_job_materialized, store, job.id, RUNNER)
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


@app.post("/rosters/{rid}/resolve")
def post_resolve(rid: int, conn=Depends(get_db)):
    """P2b partial-lock re-solve: re-run the solver holding locked=1 day cells fixed,
    re-freeze (keep locked / replace unlocked), record an undoable op='resolve' edit.
    Returns {version, grid, warnings, unlockable}. 422 with the offending cells when
    the lock set is structurally impossible or collides with a hard constraint."""
    _roster_or_404(conn, rid)
    try:
        return roster_ops.resolve_roster(conn, rid, runner=RUNNER)
    except roster_ops.LockConflictError as exc:
        raise HTTPException(status_code=422, detail=exc.conflicts)


def _format_warnings(rc: dict, month: int) -> list:
    """recompute_stats の構造化警告を検証シート用の日本語文字列へ整形。
    実際の recompute_stats キー（coverage / night_hb_gaps）に合わせる。"""
    out = []
    for u in rc.get("coverage", []):
        day = int(u["date"].split("-")[2])
        out.append(f"{month}月{day}日: [{u['location']}] の配置人数が不足しています "
                   f"(目標: {u['required']}人 / 実際: {u['assigned']}人)")
    for day in rc.get("night_hb_gaps", []):
        out.append(f"{month}月{int(day)}日: "
                   "夜勤メンバーにHB対応可能者がいないため代替処理を行いました")
    return out


@app.get("/rosters/{rid}/excel")
def get_roster_excel(rid: int, conn=Depends(get_db)):
    """凍結ロスターから Direction-A Excel を生成して配信。
    build_grid → recompute_stats(live) → render_directiona の順で派生はレンダラ外。"""
    _roster_or_404(conn, rid)
    grid, d = roster_ops.build_roster_grid(conn, rid)
    rc = roster_ops.roster_warnings(d)
    xlsx = render_directiona(grid, warnings=_format_warnings(rc, d["month"]))
    filename = f"勤務表_{d['year']}年{d['month']}月.xlsx"
    # RFC 5987: non-ASCII filenames must be percent-encoded (HTTP headers are latin-1).
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )
