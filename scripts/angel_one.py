#!/usr/bin/env python3
"""
scripts/angel_one.py
====================
Standalone CLI for everything Angel One related — connectivity checks,
portfolio inspection, manual orders, auto-trader, paper-trader, and
paper-trading reports.

Examples
--------
    # Connectivity smoke-test
    python scripts/angel_one.py status

    # Portfolio: holdings + funds + positions
    python scripts/angel_one.py portfolio

    # Place a single order (dry-run unless ANGEL_TRADING_ENABLED=1)
    python scripts/angel_one.py order --symbol RELIANCE --side BUY --qty 1
    python scripts/angel_one.py order --symbol TCS --side SELL --qty 2 \
                                     --order-type LIMIT --price 4100

    # Auto-trader (live)  — dry-run by default
    python scripts/angel_one.py auto-trade               # foreground loop
    python scripts/angel_one.py auto-trade --once        # one tick
    python scripts/angel_one.py auto-trade-status        # show state

    # Paper trader (never transmits, virtual cash)
    python scripts/angel_one.py paper-trade              # foreground loop
    python scripts/angel_one.py paper-trade --once       # one tick
    python scripts/angel_one.py paper-summary            # quick summary
    python scripts/angel_one.py paper-report             # full performance report
    python scripts/angel_one.py paper-report --send --channel telegram

This script shares the same logging setup, .env auto-load, and project
imports as `scripts/stock_analyzer.py`. The two scripts can be used
independently or together.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# UTF-8 console (Windows cp1252 default mangles ₹ and box-drawing chars)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

# Repo root on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Auto-load .env
_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from lib.logging_setup import get_logger
from src.stock_analyzer.config import LOG_FILE


# ─────────────────────────────────────────────────────────────────────
# Sub-command implementations
# ─────────────────────────────────────────────────────────────────────

def _cmd_status(args, log) -> int:
    from lib import angelone
    ok = angelone.is_available()
    log.info(f"Angel One available: {ok}")
    if not ok:
        log.error("Angel One unavailable — check creds in .env "
                  "(ANGEL_API_KEY/CLIENT_CODE/MPIN/TOTP_SECRET).")
        return 1
    holds = angelone.fetch_holdings()
    funds = angelone.fetch_funds()
    log.info(f"Holdings: {len(holds)}  Cash: ₹{funds.get('available_cash', 0):,.2f}  "
             f"Trading enabled: {angelone.trading_enabled()}")
    return 0


def _cmd_portfolio(args, log) -> int:
    from lib import angelone
    if not angelone.is_available():
        log.error("Angel One unauthenticated — set creds in .env first.")
        return 1
    holds     = angelone.fetch_holdings()
    funds     = angelone.fetch_funds()
    positions = angelone.fetch_positions()
    print("\n=== ANGEL ONE PORTFOLIO ===")
    print(f"Cash available : ₹{funds.get('available_cash', 0):>12,.2f}")
    print(f"Net worth      : ₹{funds.get('net', 0):>12,.2f}")
    print(f"Used margin    : ₹{funds.get('utilised_margin', 0):>12,.2f}")
    print(f"\nHoldings ({len(holds)}):")
    if holds:
        print(f"  {'Symbol':<14}{'Qty':>6}  {'Avg':>9}  {'LTP':>9}  {'P&L':>10}  {'%':>7}")
        tot_pnl = 0.0
        for h in holds:
            tot_pnl += float(h.get("pnl") or 0)
            print(f"  {h.get('symbol',''):<14}{h.get('qty',0):>6.0f}  "
                  f"{h.get('avg_price',0):>9,.2f}  {h.get('ltp',0):>9,.2f}  "
                  f"{h.get('pnl',0):>+10,.2f}  {h.get('pnl_pct',0):>+6.2f}%")
        print(f"  {'TOTAL':<32}{tot_pnl:>+30,.2f}")
    print(f"\nIntraday positions: {len(positions)}")
    if positions:
        for pos in positions[:10]:
            print(f"  {pos.get('tradingsymbol',''):<14} "
                  f"qty={pos.get('netqty',0)}  pnl={pos.get('pnl',0)}")
    return 0


def _cmd_order(args, log) -> int:
    from lib import angelone
    if not args.symbol or not args.side or not args.qty:
        log.error("order requires --symbol --side --qty (and --price for LIMIT/SL).")
        return 2
    result = angelone.place_order(
        symbol=args.symbol, side=args.side, qty=args.qty,
        order_type=args.order_type, product=args.product,
        price=args.price, trigger=args.trigger,
        dry_run=not angelone.trading_enabled(),
    )
    if result.get("ok"):
        mode = "DRY-RUN" if not angelone.trading_enabled() else "LIVE"
        log.info(f"[{mode}] order accepted: id={result.get('order_id')} "
                 f"msg={result.get('message')}")
        if not angelone.trading_enabled():
            log.warning("Set ANGEL_TRADING_ENABLED=1 in .env to actually send the order.")
        return 0
    log.error(f"order failed: {result.get('message')}")
    return 1


def _refresh_picks(log, force: bool = False) -> bool:
    """Run the analyzer to (re)generate today's picks.

    Returns True if a fresh report was produced. With force=False, skips the
    run when today's picks already exist on disk.
    """
    from datetime import datetime
    from src.stock_analyzer.auto_trader import _REPORTS_IDX, _REPORTS_DIR
    today = datetime.now().strftime("%Y-%m-%d")
    if not force and _REPORTS_IDX.exists():
        try:
            import json as _json
            idx = _json.loads(_REPORTS_IDX.read_text(encoding="utf-8"))
            if idx and idx[-1].startswith(today):
                log.info(f"refresh: today's picks already exist ({idx[-1]}) — skipping")
                return False
        except Exception:
            pass
    log.info("refresh: generating today's picks via analyzer (dry-run, no PDF)")
    from src.stock_analyzer.main import run_report
    run_report(dry_run=True, channel="whatsapp", theme="light",
               watchlist_path=None, make_pdf=False)
    return True


def _cmd_auto_trade(args, log) -> int:
    from src.stock_analyzer.auto_trader import TraderConfig, tick, run_loop
    if getattr(args, "refresh", False):
        _refresh_picks(log, force=True)
    cfg = TraderConfig.from_env()
    log.info(f"auto-trader config: dry_run={cfg.dry_run} "
             f"max_positions={cfg.max_positions} "
             f"max_pct_per_trade={cfg.max_pct_per_trade:.0%} "
             f"max_daily_loss=₹{cfg.max_daily_loss_inr:,.0f} "
             f"buckets={cfg.buckets} channel={cfg.notify_channel}")
    if not cfg.dry_run:
        log.warning("LIVE TRADING ENABLED — real orders will be transmitted.")
    if args.once:
        log.info(f"tick result: {tick(cfg)}")
    else:
        run_loop(cfg)
    return 0


def _cmd_paper_trade(args, log) -> int:
    from src.stock_analyzer.auto_trader import TraderConfig, tick, run_loop
    if getattr(args, "refresh", False):
        _refresh_picks(log, force=True)
    elif getattr(args, "refresh_if_stale", False):
        _refresh_picks(log, force=False)
    cfg = TraderConfig.from_env(paper=True)
    log.info(f"📝 PAPER TRADING — virtual cash ₹{cfg.paper_starting_cash:,.0f}, "
             f"max_positions={cfg.max_positions} "
             f"max_pct={cfg.max_pct_per_trade:.0%} "
             f"buckets={cfg.buckets} state=data/paper_trader_state.json")
    if args.once:
        log.info(f"tick result: {tick(cfg)}")
    else:
        run_loop(cfg)
    return 0


def _cmd_auto_trade_status(args, log) -> int:
    from src.stock_analyzer.auto_trader import TraderState
    st = TraderState.load()
    print(f"\n=== AUTO-TRADER STATE ({st.date}) ===")
    print(f"Halted        : {st.halted}  "
          f"{('(' + st.halted_reason + ')') if st.halted else ''}")
    print(f"Realised P&L  : ₹{st.realised_pnl:+,.2f}")
    print(f"\nOpen trades ({len(st.open_trades)}):")
    if st.open_trades:
        print(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'SL':>9}  {'TGT':>9}  Order")
        for t in st.open_trades:
            print(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                  f"{t.sl:>9.2f}  {t.target:>9.2f}  {t.order_id or '-'}")
    print(f"\nClosed today ({len(st.closed_today)}):")
    if st.closed_today:
        print(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'Exit':>9}  "
              f"{'P&L':>10}  Status")
        for t in st.closed_today:
            print(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                  f"{(t.exit_price or 0):>9.2f}  {t.realised_pnl:>+10.2f}  {t.status}")
    return 0


def _cmd_paper_summary(args, log) -> int:
    from src.stock_analyzer.auto_trader import TraderState, _PAPER_STATE_FILE
    st     = TraderState.load(_PAPER_STATE_FILE, paper=True)
    wins   = st.cumulative_wins
    losses = st.cumulative_losses
    total  = wins + losses
    wr     = (wins / total * 100) if total else 0
    print(f"\n=== PAPER-TRADING SUMMARY ===")
    print(f"Today           : {st.date}")
    print(f"Cumulative P&L  : ₹{st.cumulative_pnl:+,.2f}")
    print(f"Today's P&L     : ₹{st.realised_pnl:+,.2f}")
    print(f"Trades closed   : {total}  (wins {wins}  losses {losses})")
    print(f"Win rate        : {wr:.1f}%")
    print(f"\nOpen positions ({len(st.open_trades)}):")
    if st.open_trades:
        print(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'SL':>9}  {'TGT':>9}")
        for t in st.open_trades:
            print(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                  f"{t.sl:>9.2f}  {t.target:>9.2f}")
    print(f"\nClosed today ({len(st.closed_today)}):")
    if st.closed_today:
        print(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'Exit':>9}  "
              f"{'P&L':>10}  Status")
        for t in st.closed_today:
            print(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                  f"{(t.exit_price or 0):>9.2f}  {t.realised_pnl:>+10.2f}  {t.status}")
    if st.history:
        print(f"\nLast {min(10, len(st.history))} historical trades:")
        for h in st.history[-10:]:
            print(f"  {h.get('closed_at',''):<20} {h.get('symbol',''):<14} "
                  f"qty={h.get('qty',0):>3}  pnl={h.get('realised_pnl',0):>+8.2f}  "
                  f"{h.get('status','')}")
    return 0


def _cmd_paper_report(args, log) -> int:
    from src.stock_analyzer.auto_trader import TraderConfig
    from src.stock_analyzer.paper_report import build_report, save_report
    cfg  = TraderConfig.from_env(paper=True)
    text = build_report(starting_cash=cfg.paper_starting_cash)
    path = save_report(text)
    print(text)
    log.info(f"paper report saved to {path}")
    if args.send:
        try:
            from src.stock_analyzer.auto_trader import _notify
            _notify(args.channel, text)
            log.info(f"paper report sent via {args.channel}")
        except Exception as exc:
            log.warning(f"failed to send paper report: {exc}")
    return 0


# ─────────────────────────────────────────────────────────────────────
# Argparse wiring
# ─────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="angel_one",
        description="Angel One CLI — connectivity, portfolio, orders, "
                    "auto-trader, paper-trader and reports.",
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    sub.add_parser("status",    help="Login + holdings count smoke-test")
    sub.add_parser("portfolio", help="Print holdings + positions + funds")

    o = sub.add_parser("order", help="Place a single order")
    o.add_argument("--symbol",     required=True, help="Symbol e.g. RELIANCE")
    o.add_argument("--side",       required=True, choices=["BUY", "SELL"])
    o.add_argument("--qty",        required=True, type=int)
    o.add_argument("--price",      type=float, help="Limit price (LIMIT/SL only)")
    o.add_argument("--trigger",    type=float, help="Trigger price (SL/SL-M only)")
    o.add_argument("--order-type", default="MARKET",
                   choices=["MARKET", "LIMIT", "SL", "SL-M"])
    o.add_argument("--product",    default="DELIVERY",
                   choices=["DELIVERY", "INTRADAY", "MARGIN"])

    at = sub.add_parser("auto-trade",
                        help="Run live auto-trader (dry-run unless "
                             "ANGEL_TRADING_ENABLED=1 AND AUTO_TRADE_DRY_RUN=0)")
    at.add_argument("--once", action="store_true",
                    help="Single tick instead of foreground loop")
    at.add_argument("--refresh", action="store_true",
                    help="Re-run the analyzer to regenerate today's picks before trading")

    sub.add_parser("auto-trade-status",
                   help="Print live auto-trader state (open trades, P&L)")

    pt = sub.add_parser("paper-trade",
                        help="Run paper-trader (never transmits, virtual cash)")
    pt.add_argument("--once", action="store_true",
                    help="Single tick instead of foreground loop")
    pt.add_argument("--refresh", action="store_true",
                    help="Re-run the analyzer to regenerate today's picks before trading")
    pt.add_argument("--refresh-if-stale", action="store_true",
                    help="Run the analyzer only if no picks exist for today yet")

    sub.add_parser("paper-summary",
                   help="Quick paper-trading P&L + win-rate summary")

    pr = sub.add_parser("paper-report",
                        help="Full paper-trading performance report "
                             "(net P&L, profit factor, expectancy, breakdowns). "
                             "Saved to data/paper_reports/.")
    pr.add_argument("--send", action="store_true",
                    help="Push the report through the configured channel")
    pr.add_argument("--channel", default="whatsapp",
                    choices=["whatsapp", "telegram"],
                    help="Notification channel (default: whatsapp)")

    return p


# Sub-command -> handler
_HANDLERS = {
    "status":            _cmd_status,
    "portfolio":         _cmd_portfolio,
    "order":             _cmd_order,
    "auto-trade":        _cmd_auto_trade,
    "auto-trade-status": _cmd_auto_trade_status,
    "paper-trade":       _cmd_paper_trade,
    "paper-summary":     _cmd_paper_summary,
    "paper-report":      _cmd_paper_report,
}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    log  = get_logger("angel_one", LOG_FILE)
    # Mirror submodule logs to the same handlers
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in log.handlers:
        if h not in root.handlers:
            root.addHandler(h)
    log.info(f"angel_one starting … (cmd={args.cmd})")
    handler = _HANDLERS[args.cmd]
    return handler(args, log) or 0


if __name__ == "__main__":
    sys.exit(main())
