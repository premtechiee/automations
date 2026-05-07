"""Subprocess runners for triggering automations from the API.

Each runner builds an argv list, spawns ``python -u <script>`` from the repo
root, and streams stdout/stderr lines into the corresponding ``Job``.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

from .jobs import JOBS, Job
from .paths import REPO_ROOT


async def _run(job: Job) -> None:
    job.status = "running"
    job.started_at = time.time()
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = await asyncio.create_subprocess_exec(
            *job.cmd,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        async def _drain(stream: asyncio.StreamReader, sink) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                sink.append(line.decode("utf-8", errors="replace").rstrip())

        await asyncio.gather(
            _drain(proc.stdout, job.stdout),  # type: ignore[arg-type]
            _drain(proc.stderr, job.stderr),  # type: ignore[arg-type]
        )
        job.return_code = await proc.wait()
        job.status = "done" if job.return_code == 0 else "failed"
    except Exception as exc:  # pragma: no cover — defensive
        job.stderr.append(f"runner exception: {exc!r}")
        job.status = "failed"
        job.return_code = -1
    finally:
        job.finished_at = time.time()


def _python() -> str:
    return sys.executable or "python"


async def trigger_stock(flags: list[str]) -> Job:
    cmd = [_python(), "-u", "scripts/stock_analyzer.py", *flags]
    job = await JOBS.create("stock", cmd)
    asyncio.create_task(_run(job))
    return job


async def trigger_gold(flags: list[str]) -> Job:
    cmd = [_python(), "-u", "scripts/gold_notifier.py", *flags]
    job = await JOBS.create("gold", cmd)
    asyncio.create_task(_run(job))
    return job


async def trigger_paper(*, at_eod: bool, send: bool, refresh_picks: bool) -> Job:
    if send and refresh_picks:
        cmd = [_python(), "-u", "scripts/angel_one.py", "paper-trade-and-report"]
    else:
        cmd = [_python(), "-u", "scripts/angel_one.py", "paper-trade", "--once"]
        if at_eod:
            cmd.append("--at-eod")
    job = await JOBS.create("paper", cmd)
    asyncio.create_task(_run(job))
    return job
