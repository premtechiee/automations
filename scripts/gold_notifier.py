#!/usr/bin/env python3
"""
scripts/gold_notifier.py
=========================
Entry point for the gold price notifier automation.

Usage:
    python scripts/gold_notifier.py               # start the scheduler
    python scripts/gold_notifier.py --now         # run a one-shot update
    python scripts/gold_notifier.py --dry-run     # preview without sending
    python scripts/gold_notifier.py --morning     # send morning briefing
    python scripts/gold_notifier.py --afternoon   # send afternoon check
    python scripts/gold_notifier.py --check       # check alert thresholds
    python scripts/gold_notifier.py --test        # send a test WhatsApp message
"""

import argparse
import os
import sys

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
from src.gold_notifier.config import LOG_FILE
from src.gold_notifier.main import send_price_update, send_test_message
from src.gold_notifier.scheduler import (
    send_morning_briefing, send_afternoon_check,
    check_price_threshold, run_scheduler,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gold_notifier",
        description="Gold / silver price notifier with WhatsApp delivery.",
    )
    ex = p.add_mutually_exclusive_group()
    ex.add_argument("--now",       action="store_true", help="Run one-shot price update and exit.")
    ex.add_argument("--dry-run",   action="store_true", help="Fetch and preview; do NOT send.")
    ex.add_argument("--morning",   action="store_true", help="Send morning briefing.")
    ex.add_argument("--afternoon", action="store_true", help="Send afternoon check.")
    ex.add_argument("--check",     action="store_true", help="Check price alert thresholds.")
    ex.add_argument("--test",      action="store_true", help="Send a simple test WhatsApp message.")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    log = get_logger("gold_notifier_script", LOG_FILE)
    log.info("gold_notifier starting …")

    if args.test:
        send_test_message()
    elif args.now:
        send_price_update(dry_run=False)
    elif args.dry_run:
        send_price_update(dry_run=True)
    elif args.morning:
        send_morning_briefing()
    elif args.afternoon:
        send_afternoon_check()
    elif args.check:
        check_price_threshold()
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
