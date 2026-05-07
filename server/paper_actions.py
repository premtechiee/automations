"""Manual paper-trade actions exposed by the API.

These mutate ``data/paper_trader_state.json`` using the same math as
``src/angel_one/auto_trader.py`` so that hand-closed positions account for the
round-trip cost model and update cumulative stats correctly.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from .paths import PAPER_STATE


_COST_PCT_ROUND_TRIP = 0.0015  # mirrors TraderConfig default


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def close_open_position(symbol: str, exit_price: float) -> dict[str, Any]:
    """Close the open paper trade for ``symbol`` at ``exit_price``.

    Returns the updated state dict. Raises ``KeyError`` if no open trade with
    that symbol exists, ``ValueError`` if the file is missing or unparseable.
    """
    if not PAPER_STATE.exists():
        raise ValueError("paper_trader_state.json not found")
    if exit_price <= 0:
        raise ValueError("exit_price must be positive")

    raw = json.loads(PAPER_STATE.read_text(encoding="utf-8"))
    open_trades: list[dict] = list(raw.get("open_trades", []))
    closed_today: list[dict] = list(raw.get("closed_today", []))

    idx = next((i for i, t in enumerate(open_trades) if t.get("symbol") == symbol), None)
    if idx is None:
        raise KeyError(f"no open paper trade for symbol {symbol!r}")

    trade = open_trades.pop(idx)
    entry = float(trade["entry_price"])
    qty = int(trade["qty"])
    gross = (exit_price - entry) * qty
    avg_notional = ((exit_price + entry) / 2.0) * qty
    cost = avg_notional * _COST_PCT_ROUND_TRIP
    pnl = round(gross - cost, 2)

    trade["status"] = "CLOSED_MANUAL"
    trade["closed_at"] = _now()
    trade["exit_price"] = exit_price
    trade["realised_pnl"] = pnl
    closed_today.append(trade)

    raw["open_trades"] = open_trades
    raw["closed_today"] = closed_today
    raw["realised_pnl"] = round(float(raw.get("realised_pnl", 0.0)) + pnl, 2)
    raw["cumulative_pnl"] = round(float(raw.get("cumulative_pnl", 0.0)) + pnl, 2)
    if pnl >= 0:
        raw["cumulative_wins"] = int(raw.get("cumulative_wins", 0)) + 1
    else:
        raw["cumulative_losses"] = int(raw.get("cumulative_losses", 0)) + 1

    PAPER_STATE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return raw
