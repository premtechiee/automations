"""
stock_analyzer/history.py
==========================
Persist each day's recommendations and measure how prior calls played out.

Files are JSON per-run, named data/stock_reports/YYYY-MM-DD_HHMM.json,
plus a rolling index data/stock_reports/_index.json.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from typing import Any

from .config import REPORTS_DIR

logger = logging.getLogger(__name__)

_INDEX = os.path.join(REPORTS_DIR, "_index.json")


def _ensure_dir() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)


def save_report(payload: dict[str, Any]) -> str:
    _ensure_dir()
    ts   = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join(REPORTS_DIR, f"{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info(f"Saved report → {path}")

    # Update index
    idx: list[str] = []
    if os.path.exists(_INDEX):
        try:
            idx = json.load(open(_INDEX, encoding="utf-8"))
        except Exception:
            idx = []
    idx.append(os.path.basename(path))
    idx = idx[-100:]  # keep last 100
    json.dump(idx, open(_INDEX, "w", encoding="utf-8"), indent=2)
    return path


def load_previous_report() -> dict[str, Any] | None:
    """Return the most-recent saved report, or None."""
    if not os.path.exists(_INDEX):
        return None
    try:
        idx = json.load(open(_INDEX, encoding="utf-8"))
    except Exception:
        return None
    if len(idx) < 2:
        return None   # current run will be the only one
    prev_name = idx[-2]
    path = os.path.join(REPORTS_DIR, prev_name)
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def score_prior_calls(prev: dict[str, Any] | None, current_prices: dict[str, float]) -> dict[str, Any]:
    """
    For each prior recommendation, compute realised % return from the saved
    entry price to the current price. Returns hit-rate per bucket.
    """
    if not prev:
        return {"available": False}

    summary: dict[str, Any] = {"available": True, "buckets": {}}
    for bucket in ("intraday", "swing", "holding", "sell"):
        picks = prev.get("buckets", {}).get(bucket, [])
        rows, wins = [], 0
        for p in picks:
            sym = p.get("symbol"); entry = p.get("levels", {}).get("entry")
            if not sym or entry is None or sym not in current_prices:
                continue
            cur = current_prices[sym]
            ret = (cur / entry - 1) * 100
            # sell bucket wins if price dropped
            hit = ret < 0 if bucket == "sell" else ret > 0
            if hit:
                wins += 1
            rows.append({"symbol": sym, "entry": entry, "now": cur, "ret_pct": round(ret, 2), "hit": hit})
        summary["buckets"][bucket] = {
            "rows":     rows,
            "count":    len(rows),
            "wins":     wins,
            "hit_rate": round(wins / len(rows) * 100, 1) if rows else None,
        }
    return summary
