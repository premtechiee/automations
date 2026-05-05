"""
src/angel_one/config.py
========================
Channel credentials + log-file path for paper / live trading. Kept here
so the `angel_one` package does not depend on `src.stock_analyzer.*`.

All values fall through to defaults when the env var is missing OR
empty (an unset GitHub Actions secret expands to ""), so the local
defaults below act as a working-out-of-the-box fallback.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── WhatsApp (Green API) ────────────────────────────────────────────────────
PHONE_NUMBER       = os.environ.get("GOLD_PHONE_NUMBER") or "919790967892"
PHONE_NUMBERS: list[str] = [
    n.strip() for n in
    (os.environ.get("STOCK_PHONE_NUMBERS")
     or os.environ.get("GOLD_PHONE_NUMBERS")
     or f"{PHONE_NUMBER},919789990096").split(",")
    if n.strip()
]
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE") or "7107567480"
GREEN_API_TOKEN    = os.environ.get("GREEN_API_TOKEN")    or ""
GREEN_API_URL      = os.environ.get("GREEN_API_URL")      or "https://7107.api.greenapi.com"

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")   or ""

# ── Logging ─────────────────────────────────────────────────────────────────
# Per-day log file under logs/angel_one/. IST-pinned so the day rolls over
# at midnight IST regardless of where the runner is.
_IST     = timezone(timedelta(hours=5, minutes=30))
_TODAY   = datetime.now(_IST).strftime("%Y-%m-%d")
LOG_DIR  = Path("logs") / "angel_one"
LOG_FILE = str(LOG_DIR / f"{_TODAY}.log")
LOG_DIR.mkdir(parents=True, exist_ok=True)
