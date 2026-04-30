"""
src/stock_analyzer/paper_report.py
==================================
Build a rich performance report for paper-trading sessions.

Pulls everything from `data/paper_trader_state.json` (written by
`auto_trader.TraderState.save`) and computes the standard trading
metrics traders care about: win-rate, profit factor, expectancy,
average win / loss, biggest win / loss, per-symbol and per-bucket
breakdowns, plus an open-positions table.

The report is returned as a plain-text string suitable for `print`
or pushing through WhatsApp / Telegram, and is also written to
`data/paper_reports/YYYY-MM-DD_HHMM.txt` for archival.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .auto_trader import TraderState, _PAPER_STATE_FILE, OpenTrade, _now_ist

_REPORTS_DIR = Path("data") / "paper_reports"


def _trade_dicts(state: TraderState) -> list[dict]:
    """All closed trades — today + history — as plain dicts."""
    rows: list[dict] = []
    for t in state.closed_today:
        rows.append(asdict(t))
    rows.extend(state.history or [])
    return rows


def _stats(trades: Iterable[dict]) -> dict:
    """Compute headline stats for a list of closed trades."""
    trades = list(trades)
    n      = len(trades)
    wins   = [t for t in trades if (t.get("realised_pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("realised_pnl") or 0) < 0]
    flats  = [t for t in trades if (t.get("realised_pnl") or 0) == 0]

    gross_win  = sum(t["realised_pnl"] for t in wins)
    gross_loss = sum(t["realised_pnl"] for t in losses)   # negative
    net_pnl    = gross_win + gross_loss

    avg_win  = (gross_win / len(wins))    if wins   else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    win_rate = (len(wins) / n * 100)      if n      else 0.0

    profit_factor = (gross_win / abs(gross_loss)) if gross_loss else float("inf") if gross_win else 0.0
    expectancy    = (net_pnl / n)                  if n           else 0.0

    biggest_win  = max((t["realised_pnl"] for t in wins),   default=0.0)
    biggest_loss = min((t["realised_pnl"] for t in losses), default=0.0)

    return {
        "trades":        n,
        "wins":          len(wins),
        "losses":        len(losses),
        "flats":         len(flats),
        "win_rate":      win_rate,
        "gross_win":     gross_win,
        "gross_loss":    gross_loss,
        "net_pnl":       net_pnl,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "profit_factor": profit_factor,
        "expectancy":    expectancy,
        "biggest_win":   biggest_win,
        "biggest_loss":  biggest_loss,
    }


def _by_key(trades: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[str(t.get(key, "?"))].append(t)
    return {k: _stats(v) for k, v in groups.items()}


def _line(ch: str = "─", n: int = 64) -> str:
    return ch * n


def _hdr(title: str) -> str:
    return f"\n{title}\n{_line()}"


def build_report(state: TraderState | None = None,
                 starting_cash: float = 100000.0) -> str:
    """Return a multi-section text report. Pass `state` to override loading."""
    state = state or TraderState.load(_PAPER_STATE_FILE, paper=True)
    closed = _trade_dicts(state)
    s      = _stats(closed)

    cur_cash = starting_cash + state.cumulative_pnl
    pct_ret  = (state.cumulative_pnl / starting_cash * 100) if starting_cash else 0.0

    out: list[str] = []
    out.append(_line("═"))
    out.append(f"  PAPER-TRADING PERFORMANCE REPORT".center(64))
    out.append(f"  generated {_now_ist():%Y-%m-%d %H:%M IST}".center(64))
    out.append(_line("═"))

    # ── Capital ──
    out.append(_hdr("CAPITAL"))
    out.append(f"  Starting cash       : ₹{starting_cash:>14,.2f}")
    out.append(f"  Current equity*     : ₹{cur_cash:>14,.2f}   "
               f"(*excludes open MTM)")
    out.append(f"  Cumulative P&L      : ₹{state.cumulative_pnl:>+14,.2f}   "
               f"({pct_ret:+.2f}%)")
    out.append(f"  Today's realised    : ₹{state.realised_pnl:>+14,.2f}")
    if state.halted:
        out.append(f"  ⚠ HALTED            : {state.halted_reason}")

    # ── Performance ──
    out.append(_hdr("PERFORMANCE  (all closed trades)"))
    if s["trades"] == 0:
        out.append("  No closed trades yet.")
    else:
        out.append(f"  Trades closed       : {s['trades']:>14d}")
        out.append(f"  Wins / Losses       : {s['wins']:>5d} / {s['losses']:<5d}"
                   f"   (flats {s['flats']})")
        out.append(f"  Win rate            : {s['win_rate']:>13.2f}%")
        out.append(f"  Net P&L             : ₹{s['net_pnl']:>+14,.2f}")
        out.append(f"  Gross win / loss    : ₹{s['gross_win']:>+14,.2f}  /  "
                   f"₹{s['gross_loss']:>+,.2f}")
        out.append(f"  Average win         : ₹{s['avg_win']:>+14,.2f}")
        out.append(f"  Average loss        : ₹{s['avg_loss']:>+14,.2f}")
        pf = s["profit_factor"]
        pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
        out.append(f"  Profit factor       : {pf_str:>14}")
        out.append(f"  Expectancy / trade  : ₹{s['expectancy']:>+14,.2f}")
        out.append(f"  Biggest win         : ₹{s['biggest_win']:>+14,.2f}")
        out.append(f"  Biggest loss        : ₹{s['biggest_loss']:>+14,.2f}")

    # ── By bucket ──
    if closed:
        out.append(_hdr("BY BUCKET"))
        out.append(f"  {'Bucket':<10}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}  {'PF':>6}")
        for bk, st in sorted(_by_key(closed, "bucket").items()):
            pf  = st["profit_factor"]
            pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
            out.append(f"  {bk:<10}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}  {pfs:>6}")

        # ── By symbol (top 10 by |net P&L|) ──
        out.append(_hdr("BY SYMBOL  (top 10 by |net P&L|)"))
        out.append(f"  {'Symbol':<14}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}  {'PF':>6}")
        sym_stats = _by_key(closed, "symbol")
        ranked = sorted(sym_stats.items(), key=lambda kv: -abs(kv[1]["net_pnl"]))[:10]
        for sym, st in ranked:
            pf  = st["profit_factor"]
            pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
            out.append(f"  {sym:<14}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}  {pfs:>6}")

        # ── By exit reason ──
        out.append(_hdr("BY EXIT REASON"))
        out.append(f"  {'Status':<12}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}")
        for st_key, st in sorted(_by_key(closed, "status").items()):
            out.append(f"  {st_key:<12}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}")

    # ── Open positions ──
    out.append(_hdr(f"OPEN POSITIONS  ({len(state.open_trades)})"))
    if not state.open_trades:
        out.append("  (none)")
    else:
        out.append(f"  {'Symbol':<14}{'Bkt':<8}{'Qty':>5}  "
                   f"{'Entry':>9}  {'SL':>9}  {'Target':>9}  Opened")
        for t in state.open_trades:
            out.append(f"  {t.symbol:<14}{t.bucket:<8}{t.qty:>5}  "
                       f"{t.entry_price:>9.2f}  {t.sl:>9.2f}  {t.target:>9.2f}  "
                       f"{t.opened_at[:16]}")
        # Total committed capital
        committed = sum(t.entry_price * t.qty for t in state.open_trades)
        out.append(f"  {'─' * 60}")
        out.append(f"  Capital committed   : ₹{committed:>+14,.2f}")

    # ── Closed today ──
    out.append(_hdr(f"CLOSED TODAY  ({len(state.closed_today)})"))
    if not state.closed_today:
        out.append("  (none)")
    else:
        out.append(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'Exit':>9}  "
                   f"{'P&L':>11}  Status")
        for t in state.closed_today:
            ex = t.exit_price if t.exit_price is not None else 0.0
            out.append(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                       f"{ex:>9.2f}  ₹{t.realised_pnl:>+9,.2f}  {t.status}")

    # ── Recent history ──
    if state.history:
        out.append(_hdr(f"RECENT CLOSED TRADES  (last {min(15, len(state.history))})"))
        out.append(f"  {'Closed':<19}  {'Symbol':<14}{'Qty':>5}  "
                   f"{'P&L':>11}  Status")
        for h in state.history[-15:]:
            out.append(f"  {(h.get('closed_at') or '')[:19]:<19}  "
                       f"{h.get('symbol',''):<14}{h.get('qty',0):>5}  "
                       f"₹{h.get('realised_pnl',0):>+9,.2f}  "
                       f"{h.get('status','')}")

    out.append(_line("═"))
    return "\n".join(out)


def save_report(text: str) -> Path:
    """Write the report to `data/paper_reports/<timestamp>.txt` and mirror a
    copy under `logs/stock_analyzer/<date>/` for the per-run audit trail."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = _REPORTS_DIR / f"{_now_ist():%Y-%m-%d_%H%M}.txt"
    p.write_text(text, encoding="utf-8")
    try:
        from lib.logging_setup import archive_artifact
        archive_artifact("stock_analyzer", p, subdir="paper_reports")
    except Exception:
        pass
    return p
