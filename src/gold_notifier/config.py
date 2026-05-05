"""
automations/gold_notifier/config.py
====================================
All configuration constants for the Gold Price Notifier automation.
Sensitive values (GREEN_API credentials, phone) should be set via
environment variables or a .env file at the workspace root.
"""

import os
from datetime import datetime

# ── WhatsApp / Green API ────────────────────────────────────────────────────
# NOTE: Use `os.environ.get(K) or DEFAULT` (not the 2-arg form) so that an
# *empty* env var (e.g. an unset GitHub Actions secret that gets exported as
# "") still falls through to the local default instead of becoming "".
PHONE_NUMBER       = os.environ.get("GOLD_PHONE_NUMBER")    or "919790967892"
# Additional recipients (comma-separated, no spaces). Set via env or extend the default.
PHONE_NUMBERS: list[str] = [
    n.strip() for n in
    (os.environ.get("GOLD_PHONE_NUMBERS") or f"{PHONE_NUMBER},919566240454,919789990096").split(",")
    if n.strip()
]
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE")   or "7107567480"
GREEN_API_TOKEN    = os.environ.get("GREEN_API_TOKEN")      or "ba5038e7960e42c48335a62e573e0f40652c8a1df6594c67ab"
GREEN_API_URL      = os.environ.get("GREEN_API_URL")        or "https://7107.api.greenapi.com"

# ── Telegram Bot (works on PythonAnywhere free tier) ──────────────────────────
# Get a bot token from @BotFather on Telegram, then get your chat_id via:
#   https://api.telegram.org/bot<TOKEN>/getUpdates  (send any message to your bot first)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8716823723:AAGTb3TUy01RuaLHJTNxFEr4Go4DqJ9tRb4"
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")   or "8639220099"

# ── India duty/tax factors ──────────────────────────────────────────────────
# Gold:  import duty (6%) + AIDC (5%) + GST (3%) ≈ 9.4%
INDIA_GOLD_DUTY_FACTOR   = 1.094
# Silver: customs (6%) + AIDC (5%) + GST (3%) ≈ 14%
INDIA_SILVER_DUTY_FACTOR = 1.14

# ── Runtime data paths (relative to workspace root) ─────────────────────────
DATA_DIR            = "data"
PREDICTION_LOG_FILE = f"{DATA_DIR}/gold_prediction_model.json"
ALERT_STATE_FILE    = f"{DATA_DIR}/gold_alert_state.json"
# Per-automation, per-day log file under the top-level logs/ folder.
LOG_DIR             = f"logs/gold_notifier"
_TODAY              = datetime.now().strftime("%Y-%m-%d")
_RUN_DIR            = f"{LOG_DIR}/{_TODAY}"
LOG_FILE            = f"{LOG_DIR}/{_TODAY}.log"
# Generated artifacts also live under logs/ so each run is self-contained.
IMAGE_OUTPUT_PATH   = f"{_RUN_DIR}/gold_update.png"
import os as _os
_os.makedirs(_RUN_DIR, exist_ok=True)

# ── Image theme ──────────────────────────────────────────────────────────────
# Set GOLD_IMAGE_THEME=dark in your .env or GitHub secret to switch to dark mode.
# Supported values: "light" (default) | "dark"
IMAGE_THEME = os.environ.get("GOLD_IMAGE_THEME", "light").strip().lower()

# ── IST Scheduling ──────────────────────────────────────────────────────────
MORNING_UPDATE_TIME       = "10:30"   # IST daily briefing (Mon–Sat)
AFTERNOON_CHECK_TIME      = "15:00"   # IST conditional afternoon check (Mon–Sat)
PRICE_ALERT_THRESHOLD_22K = 12_500    # ₹/g — immediate alert if 22K falls below this
AFTERNOON_DROP_INR        = 500       # ₹ absolute intraday drop that triggers afternoon send
