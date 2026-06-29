import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

from shift_scheduler.src.models.schedule_result import ScheduleResult


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


@dataclass
class Job:
    id: str
    year: int
    month: int
    status: JobStatus = JobStatus.queued
    error: Optional[str] = None
    result: Optional[ScheduleResult] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, year: int, month: int) -> Job:
        job = Job(id=uuid.uuid4().hex, year=year, month=month)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


# Serialise real solves: protects CP-SAT determinism (num_workers=1) and CPU.
_solve_lock = threading.Lock()


def run_job(store: JobStore, job_id: str, runner: Callable, data_dir: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    with _solve_lock:
        job.status = JobStatus.running
        try:
            job.result = runner(job.year, job.month, data_dir)
            job.status = JobStatus.done
        except Exception as exc:  # surface failures as a failed job, not a 500
            job.error = str(exc)
            job.status = JobStatus.failed


def _resolve_request_import_id(conn, year: int, month: int):
    """Latest 予定申請 import for the month (year_month stored as 'YYYY-MM')."""
    row = conn.execute(
        "SELECT id FROM requests_import WHERE year_month=? ORDER BY id DESC LIMIT 1",
        (f"{year}-{month:02d}",)).fetchone()
    return row["id"] if row else None


def _ensure_request_file(dest_dir: str, year: int, month: int, data_dir: str) -> None:
    """Fallback so generation works before any 予定申請 upload: copy the on-disk
    予定申請.csv in as the month-suffixed name if materialize wrote none."""
    target = os.path.join(dest_dir, f"予定申請_{year}{month:02d}.csv")
    if os.path.exists(target):
        return
    src = os.path.join(data_dir, "予定申請.csv")
    if os.path.exists(src):
        shutil.copyfile(src, target)


def run_job_materialized(store: JobStore, job_id: str, runner: Callable) -> None:
    """P3 production path: materialize the default master_set (+ month 予定申請)
    into a byte-identical temp data_dir, run the safety gate, then run_schedule.
    Falls back to the on-disk data_dir when no master_set is seeded (keeps
    P1/P2 behaviour and the fast fake-runner tests green)."""
    job = store.get(job_id)
    if job is None:
        return
    # Imported here to avoid a circular import at module load (db -> masters).
    from webapp.api.config import settings, resolve_default_master_set_id
    from webapp.api.db import connect, init_db

    with _solve_lock:
        job.status = JobStatus.running
        conn = None
        tmp = None
        try:
            conn = connect(settings.db_path)
            init_db(conn)
            msid = resolve_default_master_set_id(conn)
            if msid is None:
                job.result = runner(job.year, job.month, settings.data_dir)
            else:
                from webapp.api.masters.materialize import materialize_data_dir
                from webapp.api.masters.safety import assert_load_bearing_ids
                assert_load_bearing_ids(conn, msid)  # raise -> failed job, not bad solve
                req_id = _resolve_request_import_id(conn, job.year, job.month)
                tmp = tempfile.mkdtemp(dir=settings.temp_base)
                materialize_data_dir(conn, msid, job.year, job.month, req_id, tmp)
                _ensure_request_file(tmp, job.year, job.month, settings.data_dir)
                job.result = runner(job.year, job.month, tmp)
            job.status = JobStatus.done
        except Exception as exc:  # surface failures as a failed job, not a 500
            job.error = str(exc)
            job.status = JobStatus.failed
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
            if conn is not None:
                conn.close()
