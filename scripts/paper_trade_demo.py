#!/usr/bin/env python3
"""
scripts/paper_trade_demo.py
============================
Run a SAMPLE paper-trading tick using yfinance for LTPs (no Angel One auth
required) so you can see what _decide / _apply produce against today's picks.

This is a one-shot demo:
    python scripts/paper_trade_demo.py             # one tick
    python scripts/paper_trade_demo.py --eod       # end-of-day square-off
    python scripts/paper_trade_demo.py --reset     # wipe paper state first

It bypasses the "market open" gate so you can see entries get evaluated
even on weekends / after-hours. Real GHA cron runs will obviously only
fire during market hours via the actual auto_trader.tick() path.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger("paper_trade_demo")

import yfinance as yf

import src.angel_one.auto_trader as at
from src.angel_one.auto_trader import (
    TraderConfig, TraderState, _decide, _apply, _place, _load_latest_picks,
)
from src.angel_one.paper_report import build_report


def _fetch_yf_ltps(symbols: list[str]) -> dict[str, dict]:
    """Batch-fetch last quotes via yfinance. Returns {sym: {ltp, ...}}."""
    out: dict[str, dict] = {}
    if not symbols:
        return out
    try:
        df = yf.download(
            tickers=" ".join(symbols),
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        log.warning(f"yf batch download failed: {exc}")
        df = None
    for s in symbols:
        ltp = None
        try:
            if df is not None and not df.empty:
                if len(symbols) == 1:
                    closes = df["Close"].dropna()
                else:
                    try:
                        closes = df[s]["Close"].dropna()
                    except Exception:
                        closes = None
                if closes is not None and len(closes):
                    ltp = float(closes.iloc[-1])
        except Exception as exc:
            log.warning(f"yf parse {s}: {exc}")
        if ltp:
            out[s] = {"ltp": float(ltp)}
            log.info(f"  {s:14s}  LTP Rs {ltp:.2f}")
        else:
            log.warning(f"  {s:14s}  no LTP")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eod",   action="store_true", help="EOD square-off pass")
    ap.add_argument("--reset", action="store_true", help="Reset paper state first")
    ap.add_argument("--synthetic", action="store_true",
                    help="Don't call yfinance; simulate LTPs around pick entries (fast, offline).")
    ap.add_argument("--scenario", choices=["entry", "mixed"], default="entry",
                    help="entry = open trades around pick entry; "
                         "mixed = move open positions: half hit target, half hit SL.")
    args = ap.parse_args()

    cfg = TraderConfig.from_env(paper=True)

    if args.reset and cfg.state_file.exists():
        cfg.state_file.unlink()
        log.info(f"removed {cfg.state_file}")

    # Bypass "market open" so the demo can run any time
    at.is_market_open = lambda: True   # type: ignore[assignment]

    # Bypass Angel One auth: in paper mode we shouldn't need a broker at all.
    # Replace _place with a stub that always succeeds so _apply records trades.
    def _stub_place(action, _cfg):  # type: ignore[no-redef]
        sym = (action.trade.symbol if action.trade
               else (action.pick or {}).get("symbol", "?"))
        return {"ok": True, "order_id": f"PAPER-{sym}-{action.kind}",
                "message": "paper-stub"}
    at._place = _stub_place   # type: ignore[assignment]
    # Also expose locally so the loop below uses the stub
    global _place
    _place = _stub_place  # type: ignore[assignment]

    state = TraderState.load(cfg.state_file, paper=True)
    picks = _load_latest_picks()
    if not picks:
        log.error("no picks file found in data/stock_reports/")
        return 1

    needed: set[str] = {t.symbol for t in state.open_trades}
    for bk in cfg.buckets:
        for pk in (picks.get(bk) or []):
            if pk.get("symbol"):
                needed.add(pk["symbol"])

    log.info(f"fetching LTPs for {len(needed)} symbols ...")
    if args.synthetic:
        random.seed(42)
        ltps = {}
        for bk in cfg.buckets:
            for pk in (picks.get(bk) or []):
                sym = pk.get("symbol")
                if not sym or sym not in needed:
                    continue
                anchor = (pk.get("levels") or {}).get("entry") or pk.get("price") or 100.0
                # Push price slightly above entry so trade triggers; some random variation
                ltp = anchor * (1.0 + random.uniform(-0.003, 0.004))
                ltps[sym] = {"ltp": round(float(ltp), 2)}
                log.info(f"  {sym:14s}  LTP Rs {ltp:.2f}  (synthetic)")
        # any open trades whose symbol isn't in picks: anchor on entry_price
        for t in state.open_trades:
            if t.symbol not in ltps:
                ltps[t.symbol] = {"ltp": round(t.entry_price * (1.0 + random.uniform(-0.005, 0.008)), 2)}
                log.info(f"  {t.symbol:14s}  LTP Rs {ltps[t.symbol]['ltp']:.2f}  (synthetic)")
        # In "mixed" scenario, override LTPs of OPEN positions: alternate
        # winners (move to target) and losers (move below SL) so the report
        # shows realised P&L from both sides.
        if args.scenario == "mixed":
            for i, t in enumerate(state.open_trades):
                if i % 2 == 0:
                    new_ltp = round(t.target * 1.001, 2)   # target hit
                    log.info(f"  {t.symbol:14s}  LTP Rs {new_ltp:.2f}  (TARGET overlay)")
                else:
                    new_ltp = round(t.sl * 0.999, 2)       # SL hit
                    log.info(f"  {t.symbol:14s}  LTP Rs {new_ltp:.2f}  (SL overlay)")
                ltps[t.symbol] = {"ltp": new_ltp}
    else:
        ltps = _fetch_yf_ltps(sorted(needed))
    log.info(f"got {len(ltps)} live prices")

    # For demo: re-anchor pick entry/SL/target around current LTP so the
    # entry-trigger check (within 0.5% of entry) actually fires. In a
    # real run, picks are generated minutes before market open with fresh
    # entry levels relative to live price.
    for bk in cfg.buckets:
        for pk in (picks.get(bk) or []):
            sym = pk.get("symbol")
            if not sym or sym not in ltps:
                continue
            ltp = ltps[sym]["ltp"]
            lv  = pk.setdefault("levels", {})
            entry  = ltp
            # 1.5% SL, 2.5% target -- typical intraday risk:reward
            lv["entry"]  = round(entry, 2)
            lv["sl"]     = round(entry * 0.985, 2)
            lv["target"] = round(entry * 1.025, 2)

    spent = sum(t.entry_price * t.qty for t in state.open_trades)
    funds = {"available_cash": max(0.0, cfg.paper_starting_cash
                                        + state.cumulative_pnl - spent)}

    actions = _decide(picks, state, ltps, funds, cfg, at_eod=args.eod)
    log.info(f"_decide produced {len(actions)} action(s)")
    for act in actions:
        sym = (act.trade.symbol if act.trade else (act.pick or {}).get("symbol", "?"))
        log.info(f"  {act.kind:10s}  {sym:14s}  qty={act.qty:<5d}  px={act.price:.2f}  {act.reason}")

    msgs: list[str] = []
    for act in actions:
        result = _place(act, cfg)
        msg = _apply(act, result, state, cfg)
        msgs.append(msg)
        log.info(msg)

    state.save(cfg.state_file)

    print()
    print("=" * 72)
    print("PAPER-TRADING REPORT (after demo tick)".center(72))
    print("=" * 72)
    print(build_report(state, starting_cash=cfg.paper_starting_cash))
    return 0


if __name__ == "__main__":
    sys.exit(main())

