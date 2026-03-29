"""
automations/gold_notifier/config.py
====================================
All configuration constants for the Gold Price Notifier automation.
Sensitive values (GREEN_API credentials, phone) should be set via
environment variables or a .env file at the workspace root.
"""

import os

# ── WhatsApp / Green API ────────────────────────────────────────────────────
PHONE_NUMBER       = os.environ.get("GOLD_PHONE_NUMBER",    "919790967892")
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE",   "7107567480")
GREEN_API_TOKEN    = os.environ.get("GREEN_API_TOKEN",      "ba5038e7960e42c48335a62e573e0f40652c8a1df6594c67ab")
GREEN_API_URL      = os.environ.get("GREEN_API_URL",        "https://7107.api.greenapi.com")

# ── India duty/tax factors ──────────────────────────────────────────────────
# Gold:  import duty (6%) + AIDC (5%) + GST (3%) ≈ 9.4%
INDIA_GOLD_DUTY_FACTOR   = 1.094
# Silver: customs (6%) + AIDC (5%) + GST (3%) ≈ 14%
INDIA_SILVER_DUTY_FACTOR = 1.14

# ── Runtime data paths (relative to workspace root) ─────────────────────────
DATA_DIR            = "data"
PREDICTION_LOG_FILE = f"{DATA_DIR}/gold_prediction_model.json"
ALERT_STATE_FILE    = f"{DATA_DIR}/gold_alert_state.json"
LOG_FILE            = f"{DATA_DIR}/gold_notifier.log"
IMAGE_OUTPUT_PATH   = f"{DATA_DIR}/gold_update.png"

# ── IST Scheduling ──────────────────────────────────────────────────────────
MORNING_UPDATE_TIME       = "08:00"   # IST daily briefing (Mon–Sat)
AFTERNOON_CHECK_TIME      = "14:00"   # IST conditional afternoon check (Mon–Sat)
PRICE_ALERT_THRESHOLD_22K = 12_500    # ₹/g — immediate alert if 22K falls below this
AFTERNOON_DROP_PCT        = 0.5       # % intraday drop that triggers afternoon send
