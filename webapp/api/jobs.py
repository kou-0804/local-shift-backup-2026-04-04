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
