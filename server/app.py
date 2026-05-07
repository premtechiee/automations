"""FastAPI app for the automations Android companion.

Run locally::

    uvicorn server.app:app --reload --port 8000

Production (PythonAnywhere)::

    uvicorn server.app:app --host 0.0.0.0 --port 8000

Always set ``APP_API_TOKEN`` before starting; ``server.auth`` refuses to run
without it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import paper_actions, triggers
from .auth import require_token
from .jobs import JOBS, LIMITER
from .paths import (
    GOLD_MODEL,
    LIVE_STATE,
    LOGS_GOLD_DIR,
    LOGS_STOCK_DIR,
    PAPER_REPORTS_DIR,
    PAPER_REPORTS_LAST,
    PAPER_STATE,
    STOCK_REPORTS_DIR,
    STOCK_REPORTS_INDEX,
)

app = FastAPI(
    title="Automations API",
    version="0.1.0",
    description="Read & control endpoints for the personal automations stack.",
)

# All app routes (other than /healthz) live on this router so a single bearer
# token check guards them.
api = APIRouter(dependencies=[Depends(require_token)])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{path.name} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"failed to parse {path.name}: {exc}",
        )


def _safe_child(parent: Path, name: str) -> Path:
    """Resolve ``parent / name`` and reject path traversal."""
    candidate = (parent / name).resolve()
    parent_resolved = parent.resolve()
    try:
        candidate.relative_to(parent_resolved)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid path")
    return candidate


# ── Health ──────────────────────────────────────────────────────────────────


@app.get("/healthz")  # public
def healthz() -> dict:
    return {"ok": True}


# ── Stock analyzer ─────────────────────────────────────────────────


@api.get("/stock/reports")
def stock_reports() -> dict:
    if not STOCK_REPORTS_INDEX.exists():
        return {"reports": []}
    idx = _read_json(STOCK_REPORTS_INDEX)
    if not isinstance(idx, list):
        raise HTTPException(500, "stock _index.json malformed")
    # Newest-first.
    return {"reports": list(reversed(idx))}


@api.get("/stock/latest")
def stock_latest() -> dict:
    idx = _read_json(STOCK_REPORTS_INDEX)
    if not isinstance(idx, list) or not idx:
        raise HTTPException(404, "no stock reports yet")
    name = idx[-1]
    path = _safe_child(STOCK_REPORTS_DIR, name)
    return {"name": name, "report": _read_json(path)}


@api.get("/stock/reports/{name}")
def stock_report(name: str) -> dict:
    path = _safe_child(STOCK_REPORTS_DIR, name)
    return {"name": name, "report": _read_json(path)}


# ── Gold notifier ───────────────────────────────────────────────────────────


@api.get("/gold/latest")
def gold_latest() -> dict:
    model = _read_json(GOLD_MODEL)
    if not isinstance(model, dict):
        raise HTTPException(500, "gold model malformed")
    preds = model.get("predictions") or []
    return {
        "weights": model.get("weights", {}),
        "accuracy": model.get("accuracy"),
        "bias_correction": model.get("bias_correction"),
        "latest": preds[-1] if preds else None,
        "total_predictions": len(preds),
    }


@api.get("/gold/history")
def gold_history(days: int = 30) -> dict:
    if days <= 0 or days > 1000:
        raise HTTPException(400, "days must be in 1..1000")
    model = _read_json(GOLD_MODEL)
    if not isinstance(model, dict):
        raise HTTPException(500, "gold model malformed")
    preds = list(model.get("predictions") or [])[-days:]
    return {"days": days, "predictions": preds}


# ── Paper trader ────────────────────────────────────────────────────────────


@api.get("/paper/state")
def paper_state() -> dict:
    return _read_json(PAPER_STATE)  # type: ignore[return-value]


@api.get("/paper/reports")
def paper_reports() -> dict:
    if not PAPER_REPORTS_DIR.exists():
        return {"reports": [], "last": None}
    files = sorted(
        (p.name for p in PAPER_REPORTS_DIR.iterdir() if p.is_file() and p.suffix == ".txt"),
        reverse=True,
    )
    last = None
    if PAPER_REPORTS_LAST.exists():
        last = PAPER_REPORTS_LAST.read_text(encoding="utf-8").strip() or None
    return {"reports": files, "last": last}


@api.get("/paper/reports/{name}")
def paper_report(name: str) -> dict:
    path = _safe_child(PAPER_REPORTS_DIR, name)
    if not path.exists():
        raise HTTPException(404, f"{name} not found")
    return {"name": name, "text": path.read_text(encoding="utf-8")}


class ClosePositionBody(BaseModel):
    exit_price: float = Field(..., gt=0, description="Manual exit price (>0)")


@api.post("/paper/positions/{symbol}/close")
def paper_close(symbol: str, body: ClosePositionBody) -> dict:
    try:
        new_state = paper_actions.close_open_position(symbol, body.exit_price)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"closed": symbol, "state": new_state}


# ── Live trader ─────────────────────────────────────────────────────────────


@api.get("/live/state")
def live_state() -> dict:
    if not LIVE_STATE.exists():
        # Live trader may not have been initialised yet.
        return {"date": None, "open_trades": [], "closed_today": [], "halted": False}
    return _read_json(LIVE_STATE)  # type: ignore[return-value]


# ── Static assets (PNG/PDF) ─────────────────────────────────────────────────


@api.get("/assets/stock/{date}/{name}")
def asset_stock(date: str, name: str):
    base = _safe_child(LOGS_STOCK_DIR, date)
    path = _safe_child(base, name)
    if not path.exists():
        raise HTTPException(404, f"{name} not found")
    return FileResponse(path)


@api.get("/assets/gold/{date}/{name}")
def asset_gold(date: str, name: str):
    base = _safe_child(LOGS_GOLD_DIR, date)
    path = _safe_child(base, name)
    if not path.exists():
        raise HTTPException(404, f"{name} not found")
    return FileResponse(path)


# ── Trigger endpoints ───────────────────────────────────────────────────────


_RATE_LIMITS = {
    "stock": 60.0,    # 1/min
    "gold":  60.0,
    "paper": 300.0,   # 1/5min
}


def _rate_check(key: str) -> None:
    wait = LIMITER.hit(key, _RATE_LIMITS.get(key, 60.0))
    if wait > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"rate-limited; retry in {wait:.0f}s",
        )


_ALLOWED_STOCK_FLAGS = {
    "--now", "--dry-run", "--preopen", "--morning", "--afternoon", "--test",
    "--no-pdf",
}
_ALLOWED_GOLD_FLAGS = {"--now", "--dry-run", "--morning", "--afternoon", "--check", "--test"}


class StockRunBody(BaseModel):
    flags: list[str] = Field(default_factory=lambda: ["--now"])
    channel: str | None = Field(default=None, pattern="^(whatsapp|telegram|none)$")
    theme: str | None = Field(default=None, pattern="^(light|dark)$")


@api.post("/stock/run")
async def stock_run(body: StockRunBody) -> dict:
    _rate_check("stock")
    flags = list(body.flags)
    for f in flags:
        if f not in _ALLOWED_STOCK_FLAGS:
            raise HTTPException(400, f"flag not allowed: {f}")
    if body.channel:
        flags += ["--channel", body.channel]
    if body.theme:
        flags += ["--theme", body.theme]
    job = await triggers.trigger_stock(flags)
    return {"job": job.to_dict()}


class GoldRunBody(BaseModel):
    flags: list[str] = Field(default_factory=lambda: ["--now"])


@api.post("/gold/run")
async def gold_run(body: GoldRunBody) -> dict:
    _rate_check("gold")
    flags = list(body.flags)
    for f in flags:
        if f not in _ALLOWED_GOLD_FLAGS:
            raise HTTPException(400, f"flag not allowed: {f}")
    job = await triggers.trigger_gold(flags)
    return {"job": job.to_dict()}


class PaperRunBody(BaseModel):
    at_eod: bool = False
    send: bool = False
    refresh_picks: bool = False  # if True with send=True, runs paper-trade-and-report


@api.post("/paper/run")
async def paper_run(body: PaperRunBody) -> dict:
    _rate_check("paper")
    job = await triggers.trigger_paper(
        at_eod=body.at_eod, send=body.send, refresh_picks=body.refresh_picks
    )
    return {"job": job.to_dict()}


@api.get("/jobs")
def jobs_list() -> dict:
    return {"jobs": [j.to_dict() for j in JOBS.list()]}


@api.get("/jobs/{job_id}")
def jobs_get(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


app.include_router(api)


# ── Error formatting ────────────────────────────────────────────────────────


@app.exception_handler(HTTPException)
async def _http_exc(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status": exc.status_code},
        headers=exc.headers,
    )
