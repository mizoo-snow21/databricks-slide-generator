"""Demo-grade in-memory deck generation job store (single-process)."""

from __future__ import annotations

import copy
import threading
import uuid
from concurrent import futures
from dataclasses import dataclass, replace
from typing import Any, Optional

_JOB_RUNNING = "running"
_JOB_DONE = "done"
_JOB_ERROR = "error"


@dataclass
class DeckJob:
    id: str
    status: str
    created_at: float
    kind: str = "deck"
    deck_id: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    status_code: Optional[int] = None


def _snapshot_job(job: DeckJob) -> DeckJob:
    if job.result is not None:
        return replace(job, result=copy.deepcopy(job.result))
    return replace(job)


class DeckJobStore:
    def __init__(self, max_jobs: int = 50) -> None:
        self._max_jobs = max_jobs
        self._lock = threading.Lock()
        self._jobs: dict[str, DeckJob] = {}
        self._futures: dict[str, futures.Future[Any]] = {}

    def create(self, now: float, kind: str = "deck") -> DeckJob:
        with self._lock:
            job_id = uuid.uuid4().hex
            job = DeckJob(id=job_id, status=_JOB_RUNNING, created_at=now, kind=kind)
            self._jobs[job_id] = job
            self._prune_unlocked()
            return _snapshot_job(job)

    def attach_future(self, job_id: str, future: futures.Future[Any]) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._futures[job_id] = future

    def set_done(
        self,
        job_id: str,
        deck_id: str | None = None,
        *,
        result: Any = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            updates: dict[str, Any] = {"status": _JOB_DONE}
            if deck_id is not None:
                updates["deck_id"] = deck_id
            if result is not None:
                updates["result"] = result
            self._jobs[job_id] = replace(job, **updates)

    def set_error(self, job_id: str, error: str, status_code: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._jobs[job_id] = replace(
                job, status=_JOB_ERROR, error=error, status_code=status_code
            )

    def get(self, job_id: str) -> Optional[DeckJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return _snapshot_job(job)

    def wait(self, job_id: str, timeout: float) -> Optional[DeckJob]:
        future: futures.Future[Any] | None = None
        with self._lock:
            if job_id not in self._jobs:
                return None
            future = self._futures.get(job_id)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except Exception:
                pass
        return self.get(job_id)

    def prune(self) -> None:
        with self._lock:
            self._prune_unlocked()

    def _prune_unlocked(self) -> None:
        excess = len(self._jobs) - self._max_jobs
        if excess <= 0:
            return
        sorted_ids = sorted(self._jobs, key=lambda k: self._jobs[k].created_at)
        for job_id in sorted_ids[:excess]:
            del self._jobs[job_id]
            self._futures.pop(job_id, None)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._futures.clear()
