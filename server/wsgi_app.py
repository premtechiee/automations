"""Flask WSGI shim of the automations API.

Exists so the server can run under uWSGI on PythonAnywhere without an
ASGI→WSGI bridge (a2wsgi deadlocks under uWSGI's single-worker model). All
endpoints mirror :mod:`server.app` exactly so the Android client can talk to
either backend interchangeably.

Usage in ``/var/www/<you>_pythonanywhere_com_wsgi.py``::

    import os, sys
    os.environ['APP_API_TOKEN'] = '...'
    path = '/home/<you>/automations'
    if path not in sys.path:
        sys.path.insert(0, path)
    from server.wsgi_app import app as application
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_file

from .paths import (
    GOLD_MODEL,
    LIVE_STATE,
    LOGS_GOLD_DIR,
    LOGS_STOCK_DIR,
    PAPER_REPORTS_DIR,
    PAPER_REPORTS_LAST,
    PAPER_STATE,
    REPO_ROOT,
    STOCK_REPORTS_DIR,
    STOCK_REPORTS_INDEX,
)
from . import paper_actions

app = Flask(__name__)


# ── Auth ─────────────────────────────────────────────────────────────────────


def _expected_token() -> str:
    tok = os.environ.get("APP_API_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("APP_API_TOKEN env var not set")
    return tok


def _check_auth() -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        abort(401, "Missing bearer token")
    presented = auth.split(None, 1)[1].strip()
    if not secrets.compare_digest(presented, _expected_token()):
        abort(401, "Invalid token")


@app.before_request
def _gate() -> None:
    if request.path == "/healthz":
        return None
    _check_auth()
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_json(path: Path):
    if not path.exists():
        abort(404, f"{path.name} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        abort(500, f"failed to parse {path.name}: {exc}")


def _safe_child(parent: Path, name: str) -> Path:
    candidate = (parent / name).resolve()
    parent_resolved = parent.resolve()
    try:
        candidate.relative_to(parent_resolved)
    except ValueError:
        abort(400, "invalid path")
    return candidate


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


# ── Stock analyzer ───────────────────────────────────────────────────────────


@app.get("/stock/reports")
def stock_reports():
    if not STOCK_REPORTS_INDEX.exists():
        return jsonify(reports=[])
    idx = _read_json(STOCK_REPORTS_INDEX)
    if not isinstance(idx, list):
        abort(500, "stock _index.json malformed")
    return jsonify(reports=list(reversed(idx)))


@app.get("/stock/latest")
def stock_latest():
    idx = _read_json(STOCK_REPORTS_INDEX)
    if not isinstance(idx, list) or not idx:
        abort(404, "no stock reports yet")
    name = idx[-1]
    path = _safe_child(STOCK_REPORTS_DIR, name)
    return jsonify(name=name, report=_read_json(path))


@app.get("/stock/reports/<name>")
def stock_report(name: str):
    path = _safe_child(STOCK_REPORTS_DIR, name)
    return jsonify(name=name, report=_read_json(path))


# ── Gold notifier ────────────────────────────────────────────────────────────


@app.get("/gold/latest")
def gold_latest():
    model = _read_json(GOLD_MODEL)
    if not isinstance(model, dict):
        abort(500, "gold model malformed")
    preds = model.get("predictions") or []
    return jsonify(
        weights=model.get("weights", {}),
        accuracy=model.get("accuracy"),
        bias_correction=model.get("bias_correction"),
        latest=preds[-1] if preds else None,
        total_predictions=len(preds),
    )


@app.get("/gold/history")
def gold_history():
    try:
        days = int(request.args.get("days", "30"))
    except ValueError:
        abort(400, "days must be integer")
    if days <= 0 or days > 1000:
        abort(400, "days must be in 1..1000")
    model = _read_json(GOLD_MODEL)
    if not isinstance(model, dict):
        abort(500, "gold model malformed")
    preds = list(model.get("predictions") or [])[-days:]
    return jsonify(days=days, predictions=preds)


# ── Paper trader ─────────────────────────────────────────────────────────────


@app.get("/paper/state")
def paper_state():
    return jsonify(_read_json(PAPER_STATE))


@app.get("/paper/reports")
def paper_reports():
    if not PAPER_REPORTS_DIR.exists():
        return jsonify(reports=[], last=None)
    files = sorted(
        (p.name for p in PAPER_REPORTS_DIR.iterdir() if p.is_file() and p.suffix == ".txt"),
        reverse=True,
    )
    last = None
    if PAPER_REPORTS_LAST.exists():
        last = PAPER_REPORTS_LAST.read_text(encoding="utf-8").strip() or None
    return jsonify(reports=files, last=last)


@app.get("/paper/reports/<name>")
def paper_report(name: str):
    path = _safe_child(PAPER_REPORTS_DIR, name)
    if not path.exists():
        abort(404, f"{name} not found")
    return jsonify(name=name, text=path.read_text(encoding="utf-8"))


@app.post("/paper/positions/<symbol>/close")
def paper_close(symbol: str):
    body = request.get_json(silent=True) or {}
    try:
        exit_price = float(body.get("exit_price"))
    except (TypeError, ValueError):
        abort(400, "exit_price must be a number")
    if exit_price <= 0:
        abort(400, "exit_price must be > 0")
    try:
        new_state = paper_actions.close_open_position(symbol, exit_price)
    except KeyError as exc:
        abort(404, str(exc))
    except ValueError as exc:
        abort(400, str(exc))
    return jsonify(closed=symbol, state=new_state)


# ── Live trader ──────────────────────────────────────────────────────────────


@app.get("/live/state")
def live_state():
    if not LIVE_STATE.exists():
        return jsonify(date=None, open_trades=[], closed_today=[], halted=False)
    return jsonify(_read_json(LIVE_STATE))


# ── Static assets ────────────────────────────────────────────────────────────


@app.get("/assets/stock/<date>/<name>")
def asset_stock(date: str, name: str):
    base = _safe_child(LOGS_STOCK_DIR, date)
    path = _safe_child(base, name)
    if not path.exists():
        abort(404, f"{name} not found")
    return send_file(path)


@app.get("/assets/gold/<date>/<name>")
def asset_gold(date: str, name: str):
    base = _safe_child(LOGS_GOLD_DIR, date)
    path = _safe_child(base, name)
    if not path.exists():
        abort(404, f"{name} not found")
    return send_file(path)


# ── Job runner (threaded subprocess; no asyncio) ─────────────────────────────


_JOBS: "dict[str, dict]" = {}
_JOB_ORDER: "deque[str]" = deque(maxlen=50)
_JOB_LOCK = threading.Lock()
_LAST_HIT: "dict[str, float]" = {}
_RATE_LIMITS = {"stock": 60.0, "gold": 60.0, "paper": 300.0}


def _rate_check(key: str) -> None:
    now = time.monotonic()
    last = _LAST_HIT.get(key, 0.0)
    elapsed = now - last
    interval = _RATE_LIMITS.get(key, 60.0)
    if elapsed < interval:
        abort(429, f"rate-limited; retry in {interval - elapsed:.0f}s")
    _LAST_HIT[key] = now


def _job_create(kind: str, cmd: list[str]) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "cmd": cmd,
        "status": "pending",
        "started_at": 0.0,
        "finished_at": 0.0,
        "return_code": None,
        "stdout_tail": [],
        "stderr_tail": [],
    }
    with _JOB_LOCK:
        if len(_JOB_ORDER) == _JOB_ORDER.maxlen:
            _JOBS.pop(_JOB_ORDER[0], None)
        _JOBS[job["id"]] = job
        _JOB_ORDER.append(job["id"])
    return job


def _job_run(job: dict) -> None:
    job["status"] = "running"
    job["started_at"] = time.time()
    out_tail: deque[str] = deque(maxlen=400)
    err_tail: deque[str] = deque(maxlen=400)
    job["stdout_tail"] = out_tail  # type: ignore[assignment]
    job["stderr_tail"] = err_tail  # type: ignore[assignment]
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        proc = subprocess.Popen(
            job["cmd"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )

        def _drain(stream, sink: deque[str]) -> None:
            for line in stream:
                sink.append(line.rstrip())

        t_out = threading.Thread(target=_drain, args=(proc.stdout, out_tail), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, err_tail), daemon=True)
        t_out.start(); t_err.start()
        rc = proc.wait()
        t_out.join(timeout=5); t_err.join(timeout=5)
        job["return_code"] = rc
        job["status"] = "done" if rc == 0 else "failed"
    except Exception as exc:
        err_tail.append(f"runner exception: {exc!r}")
        job["status"] = "failed"
        job["return_code"] = -1
    finally:
        job["finished_at"] = time.time()
        # Materialise the deques for JSON output.
        job["stdout_tail"] = list(out_tail)
        job["stderr_tail"] = list(err_tail)


def _spawn(kind: str, cmd: list[str]) -> dict:
    job = _job_create(kind, cmd)
    threading.Thread(target=_job_run, args=(job,), daemon=True).start()
    return job


def _python() -> str:
    return sys.executable or "python"


_ALLOWED_STOCK_FLAGS = {
    "--now", "--dry-run", "--preopen", "--morning", "--afternoon", "--test", "--no-pdf",
}
_ALLOWED_GOLD_FLAGS = {"--now", "--dry-run", "--morning", "--afternoon", "--check", "--test"}


@app.post("/stock/run")
def stock_run():
    _rate_check("stock")
    body = request.get_json(silent=True) or {}
    flags: list[str] = list(body.get("flags") or ["--now"])
    for f in flags:
        if f not in _ALLOWED_STOCK_FLAGS:
            abort(400, f"flag not allowed: {f}")
    channel = body.get("channel")
    theme = body.get("theme")
    if channel and channel not in {"whatsapp", "telegram", "none"}:
        abort(400, "invalid channel")
    if theme and theme not in {"light", "dark"}:
        abort(400, "invalid theme")
    if channel:
        flags += ["--channel", channel]
    if theme:
        flags += ["--theme", theme]
    cmd = [_python(), "-u", "scripts/stock_analyzer.py", *flags]
    return jsonify(job=_spawn("stock", cmd))


@app.post("/gold/run")
def gold_run():
    _rate_check("gold")
    body = request.get_json(silent=True) or {}
    flags: list[str] = list(body.get("flags") or ["--now"])
    for f in flags:
        if f not in _ALLOWED_GOLD_FLAGS:
            abort(400, f"flag not allowed: {f}")
    cmd = [_python(), "-u", "scripts/gold_notifier.py", *flags]
    return jsonify(job=_spawn("gold", cmd))


@app.post("/paper/run")
def paper_run():
    _rate_check("paper")
    body = request.get_json(silent=True) or {}
    at_eod = bool(body.get("at_eod", False))
    send = bool(body.get("send", False))
    refresh_picks = bool(body.get("refresh_picks", False))
    if send and refresh_picks:
        cmd = [_python(), "-u", "scripts/angel_one.py", "paper-trade-and-report"]
    else:
        cmd = [_python(), "-u", "scripts/angel_one.py", "paper-trade", "--once"]
        if at_eod:
            cmd.append("--at-eod")
    return jsonify(job=_spawn("paper", cmd))


@app.get("/jobs")
def jobs_list():
    with _JOB_LOCK:
        items = [_JOBS[j] for j in _JOB_ORDER if j in _JOBS]
    # deque tails materialise on completion; while running, snapshot now.
    out = []
    for j in items:
        snap = dict(j)
        if isinstance(snap.get("stdout_tail"), deque):
            snap["stdout_tail"] = list(snap["stdout_tail"])
        if isinstance(snap.get("stderr_tail"), deque):
            snap["stderr_tail"] = list(snap["stderr_tail"])
        out.append(snap)
    return jsonify(jobs=out)


@app.get("/jobs/<job_id>")
def jobs_get(job_id: str):
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        abort(404, "job not found")
    snap = dict(job)
    if isinstance(snap.get("stdout_tail"), deque):
        snap["stdout_tail"] = list(snap["stdout_tail"])
    if isinstance(snap.get("stderr_tail"), deque):
        snap["stderr_tail"] = list(snap["stderr_tail"])
    return jsonify(snap)


# ── Error formatting ─────────────────────────────────────────────────────────


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
@app.errorhandler(429)
@app.errorhandler(500)
def _err(e):
    code = getattr(e, "code", 500) or 500
    desc = getattr(e, "description", str(e))
    resp = jsonify(error=desc, status=code)
    resp.status_code = code
    if code == 401:
        resp.headers["WWW-Authenticate"] = "Bearer"
    return resp
