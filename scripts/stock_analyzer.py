#!/usr/bin/env python3
"""
scripts/stock_analyzer.py
==========================
Entry point for the Indian stock & mutual-fund analyzer.

Analyses NIFTY-50 universe with:
  • Technicals (EMA trend, RSI, MACD, ATR, Bollinger, volume)
  • Fundamentals (P/E, P/B, ROE, D/E, growth, margins)
  • Headline sentiment (naive keyword scoring)
and emits four buckets — Intraday / Swing / Holding / Sell — plus a
ranked mutual-fund table. A PNG report is generated and optionally
sent via WhatsApp or Telegram.

Usage:
    python scripts/stock_analyzer.py --dry-run          # no send, full console log
    python scripts/stock_analyzer.py --now              # send via WhatsApp
    python scripts/stock_analyzer.py --now --channel telegram
    python scripts/stock_analyzer.py --test             # send a ping to verify delivery
    python scripts/stock_analyzer.py --theme light      # override theme
"""

import argparse
import os
import sys

# On Windows, reconfigure stdout/stderr to UTF-8 so emojis & box-drawing chars
# in the console dry-run output don't crash the interpreter (cp1252 default).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

# Allow running from the repo root without installing the package
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Auto-load .env file from repo root (must happen before any lib imports)
_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from lib.logging_setup import get_logger
from src.stock_analyzer.config import LOG_FILE, IMAGE_THEME as _DEFAULT_THEME
from src.stock_analyzer.main import run_report, send_test_message
import logging


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock_analyzer",
        description="Indian stock & MF analyser with WhatsApp/Telegram delivery.",
    )
    p.add_argument("--channel", choices=["whatsapp", "telegram"], default="whatsapp",
                   help="Notification channel (default: whatsapp).")
    p.add_argument("--theme", choices=["light", "dark"], default=_DEFAULT_THEME,
                   help="Image theme (default: dark).")
    p.add_argument("--limit", type=int, default=0,
                   help="Limit universe to first N symbols (0 = no limit). Useful for quick tests.")
    p.add_argument("--watchlist", type=str, default=None,
                   help="Path to watchlist file (default: data/stock_watchlist.txt).")
    p.add_argument("--no-pdf", action="store_true",
                   help="Skip PDF generation (image + console only).")
    ex = p.add_mutually_exclusive_group()
    ex.add_argument("--now",       action="store_true", help="Run analysis and send report.")
    ex.add_argument("--preopen",   action="store_true",
                    help="Pre-open briefing (08:00 IST) — US close + swing picks for today.")
    ex.add_argument("--morning",   action="store_true",
                    help="Market-open confirmation (09:30 IST) — validate trades after first 15 min.")
    ex.add_argument("--afternoon", action="store_true",
                    help="Mid-session update (14:00 IST) — trend update + hold/sell guidance.")
    ex.add_argument("--dry-run",   action="store_true", help="Run analysis, print to console, do NOT send.")
    ex.add_argument("--test",      action="store_true", help="Send a test ping only.")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    log = get_logger("stock_analyzer_script", LOG_FILE)
    # Also route all sub-module (lib.*, src.stock_analyzer.*) logs through
    # the same handlers so progress is visible in the terminal for dry-run.
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in log.handlers:
        if h not in root.handlers:
            root.addHandler(h)
    log.info(f"stock_analyzer starting … (channel={args.channel}, theme={args.theme})")

    # Apply universe limit via env var so the library picks it up.
    if args.limit > 0:
        os.environ["STOCK_UNIVERSE_LIMIT"] = str(args.limit)

    if args.test:
        send_test_message(channel=args.channel)
    elif args.dry_run:
        run_report(dry_run=True,  channel=args.channel, theme=args.theme,
                   watchlist_path=args.watchlist, make_pdf=not args.no_pdf)
    elif args.preopen:
        os.environ["STOCK_SESSION"]       = "preopen"
        os.environ["STOCK_SESSION_LABEL"] = (
            "🌅 PRE-OPEN BRIEF (08:00 IST) — US Market Close + Today's Swing Picks"
        )
        run_report(dry_run=False, channel=args.channel, theme=args.theme,
                   watchlist_path=args.watchlist, make_pdf=not args.no_pdf)
    elif args.morning:
        os.environ["STOCK_SESSION"]       = "morning"
        os.environ["STOCK_SESSION_LABEL"] = (
            "🔔 MARKET OPEN CONFIRMATION (09:30 IST) — Validated Trades After First 15 min"
        )
        run_report(dry_run=False, channel=args.channel, theme=args.theme,
                   watchlist_path=args.watchlist, make_pdf=not args.no_pdf)
    elif args.afternoon:
        os.environ["STOCK_SESSION"]       = "afternoon"
        os.environ["STOCK_SESSION_LABEL"] = (
            "🕒 MID-SESSION UPDATE (14:00 IST) — Market Trend & Active Trade Calls"
        )
        run_report(dry_run=False, channel=args.channel, theme=args.theme,
                   watchlist_path=args.watchlist, make_pdf=not args.no_pdf)
    else:
        # default behaviour = --now
        run_report(dry_run=False, channel=args.channel, theme=args.theme,
                   watchlist_path=args.watchlist, make_pdf=not args.no_pdf)


if __name__ == "__main__":
    main()
