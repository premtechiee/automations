"""In-memory async job store + per-route rate limiter.

The store is intentionally tiny (no persistence, no queue): a job represents a
subprocess that runs an automation script. Survives only for the lifetime of
the FastAPI process, which is fine for a single-user companion app.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

JobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class Job:
    id: str
    kind: str
    cmd: list[str]
    status: JobStatus = "pending"
    started_at: float = 0.0
    finished_at: float = 0.0
    return_code: int | None = None
    stdout: deque[str] = field(default_factory=lambda: deque(maxlen=400))
    stderr: deque[str] = field(default_factory=lambda: deque(maxlen=400))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "cmd": self.cmd,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "stdout_tail": list(self.stdout),
            "stderr_tail": list(self.stderr),
        }


class JobStore:
    def __init__(self, max_jobs: int = 50) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: deque[str] = deque(maxlen=max_jobs)
        self._lock = asyncio.Lock()

    async def create(self, kind: str, cmd: list[str]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, cmd=cmd)
        async with self._lock:
            # Evict oldest if at capacity.
            if len(self._order) == self._order.maxlen:
                oldest = self._order[0]
                self._jobs.pop(oldest, None)
            self._jobs[job.id] = job
            self._order.append(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return [self._jobs[j] for j in self._order if j in self._jobs]


JOBS = JobStore()


class RateLimiter:
    """Simple token-bucket per route key (in-memory, single-process).

    Not perfect for multi-worker deployments but PythonAnywhere typically
    serves this app from a single worker.
    """

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def hit(self, key: str, min_interval_sec: float) -> float:
        """Returns 0 if allowed, else the seconds to wait."""
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        elapsed = now - last
        if elapsed < min_interval_sec:
            return min_interval_sec - elapsed
        self._last[key] = now
        return 0.0


LIMITER = RateLimiter()
