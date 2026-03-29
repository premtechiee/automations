"""
automations/gold_notifier/scheduler.py
=========================================
IST-aware smart scheduler: morning briefing, afternoon conditional check,
and price-threshold guard.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

from .config import (
    MORNING_UPDATE_TIME, AFTERNOON_CHECK_TIME,
    PRICE_ALERT_THRESHOLD_22K, AFTERNOON_DROP_INR, ALERT_STATE_FILE,
)
from .fetchers import _fetch_goodreturns_history, get_gold_price
from .analysis import get_geopolitical_analysis, get_global_market_signals
from lib.whatsapp import send_message as _send_msg
from lib import telegram as _tg
from .config import PHONE_NUMBER, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from lib.proxy import PROXIES

logger = logging.getLogger(__name__)
_IST   = timezone(timedelta(hours=5, minutes=30))


def _ist_now() -> datetime:
    return datetime.now(_IST)


def _is_market_day(dt: datetime | None = None) -> bool:
    """Mon–Sat are market days; Sunday is not."""
    if dt is None:
        dt = _ist_now()
    return dt.weekday() < 6


def _load_alert_state() -> dict:
    try:
        if os.path.exists(ALERT_STATE_FILE):
            with open(ALERT_STATE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception as exc:
        logger.warning(f"Could not load alert state: {exc}")
    return {}


def _save_alert_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(ALERT_STATE_FILE) or ".", exist_ok=True)
        with open(ALERT_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, default=str)
    except Exception as exc:
        logger.warning(f"Could not save alert state: {exc}")


def _get_quick_price_22k() -> int | None:
    try:
        rows = _fetch_goodreturns_history()
        if rows:
            return rows[0]["22k"]
    except Exception:
        pass
    try:
        data = get_gold_price()
        if data:
            from .config import INDIA_GOLD_DUTY_FACTOR
            return round(data.get("price_inr_per_g", 0) * INDIA_GOLD_DUTY_FACTOR * 22 / 24)
    except Exception:
        pass
    return None


def _notify_alert(message: str, channel: str = "whatsapp") -> bool:
    """Send an alert via Telegram or WhatsApp depending on `channel`."""
    if channel == "telegram":
        return _tg.send_message(TELEGRAM_CHAT_ID, message, TELEGRAM_BOT_TOKEN, PROXIES)
    return _send_msg(PHONE_NUMBER, message, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, PROXIES)


def send_morning_briefing(channel: str = "whatsapp") -> None:
    """Full 8:00 AM IST morning briefing — skips Sundays."""
    from .main import send_price_update
    now_ist = _ist_now()
    if not _is_market_day(now_ist):
        logger.info("[MORNING] Sunday — skipping morning briefing.")
        return
    logger.info("[MORNING] Sending morning briefing …")
    send_price_update(channel=channel)
    try:
        rows = _fetch_goodreturns_history()
        if rows:
            state = _load_alert_state()
            state["morning_price_22k"] = rows[0]["22k"]
            state["morning_date"]      = str(now_ist.date())
            _save_alert_state(state)
            logger.info(f"[MORNING] Snapshot saved — 22K opening price: ₹{rows[0]['22k']:,}/g")
    except Exception as exc:
        logger.warning(f"[MORNING] Could not snapshot opening price: {exc}")


def send_afternoon_check(channel: str = "whatsapp") -> None:
    """
    2:00 PM IST conditional alert — sends only if a trigger fires:
      1. 22K dropped ≥ ₹AFTERNOON_DROP_INR since this morning
      2. Geopolitical escalation (geo_score ≥ 2)
      3. Global macro net_score ≤ -3
    """
    from .main import send_price_update
    now_ist = _ist_now()
    if not _is_market_day(now_ist):
        logger.info("[AFTERNOON] Sunday — skipping afternoon check.")
        return

    logger.info("[AFTERNOON] Running afternoon market check …")
    state     = _load_alert_state()
    today_str = str(now_ist.date())
    triggers  = []

    curr_22k = _get_quick_price_22k()
    if curr_22k is None:
        logger.warning("[AFTERNOON] Could not fetch current price — aborting check.")
        return

    morning_22k  = state.get("morning_price_22k")
    morning_date = state.get("morning_date")
    if morning_22k and morning_date == today_str:
        drop = morning_22k - curr_22k
        if drop >= AFTERNOON_DROP_INR:
            triggers.append(f"📉 Price dropped ₹{drop:,}/g since morning (₹{morning_22k:,} → ₹{curr_22k:,})")
            logger.info(f"[AFTERNOON] TRIGGER price drop: ₹{drop:,}  (₹{morning_22k:,} → ₹{curr_22k:,})")
    else:
        logger.info("[AFTERNOON] No morning snapshot for today — skipping drift check.")

    try:
        geo = get_geopolitical_analysis()
        if geo and geo.get("geo_score", 0) >= 2:
            triggers.append(f"🔴 Geopolitical alert: {geo['geo_signal']}")
    except Exception as exc:
        logger.warning(f"[AFTERNOON] Geo analysis error: {exc}")

    try:
        global_signals = get_global_market_signals()
        if global_signals and global_signals.get("net_score", 0) <= -3:
            triggers.append(f"⚠️ Market signals bearish: net_score={global_signals['net_score']}")
    except Exception as exc:
        logger.warning(f"[AFTERNOON] Global signals error: {exc}")

    if triggers:
        trigger_lines = "\n".join(f"  • {t}" for t in triggers)
        logger.info(f"[AFTERNOON] {len(triggers)} trigger(s) fired — sending update.")
        _notify_alert(
            f"🔔 *Afternoon Gold Alert*\n\n"
            f"Market update triggered at 2 PM IST:\n{trigger_lines}\n\n"
            f"Full analysis below ↓",
            channel,
        )
        send_price_update(channel=channel)
    else:
        logger.info(
            f"[AFTERNOON] No triggers (22K=₹{curr_22k:,}/g) — skipping send."
        )


def check_price_threshold(channel: str = "whatsapp") -> None:
    """Immediate alert if 22K < PRICE_ALERT_THRESHOLD_22K (deduplicated per day)."""
    from .main import send_price_update
    curr_22k = _get_quick_price_22k()
    if curr_22k is None or curr_22k >= PRICE_ALERT_THRESHOLD_22K:
        return

    today_str = str(_ist_now().date())
    state     = _load_alert_state()
    if state.get("last_threshold_breach_date") == today_str:
        return

    logger.info(f"[THRESHOLD] ⚠️  22K=₹{curr_22k:,} below ₹{PRICE_ALERT_THRESHOLD_22K:,} — sending IMMEDIATE alert!")
    state["last_threshold_breach_date"] = today_str
    _save_alert_state(state)
    _notify_alert(
        f"🚨 *IMMEDIATE GOLD PRICE ALERT* 🚨\n\n"
        f"🔻 22 Carat gold has fallen BELOW ₹{PRICE_ALERT_THRESHOLD_22K:,}/g!\n\n"
        f"  Current 22K price : ₹{curr_22k:,}/g\n"
        f"  Your alert level  : ₹{PRICE_ALERT_THRESHOLD_22K:,}/g\n\n"
        f"💡 Consider this a potential buying opportunity window.\n"
        f"📊 Full market analysis follows ↓",
        channel,
    )
    send_price_update(channel=channel)


def run_scheduler(channel: str = "whatsapp") -> None:
    """
    IST-aware smart scheduler:
      1) 08:00 IST — morning briefing (Mon–Sat)
      2) 14:00 IST — conditional afternoon check (Mon–Sat)
      3) Every 10 min — price threshold guard (Mon–Sat)
    """
    logger.info("=" * 60)
    logger.info("Gold Price Notifier — Smart IST Scheduler started")
    logger.info(f"  Channel          : {channel}")
    logger.info(f"  Target number    : {PHONE_NUMBER}")
    logger.info(f"  Morning briefing : {MORNING_UPDATE_TIME} IST  (Mon–Sat)")
    logger.info(f"  Afternoon check  : {AFTERNOON_CHECK_TIME} IST  (Mon–Sat, conditional)")
    logger.info(f"  Threshold guard  : every 10 min — alert if 22K < ₹{PRICE_ALERT_THRESHOLD_22K:,}/g")
    logger.info("=" * 60)

    _last_morning_date   = None
    _last_afternoon_date = None
    _last_threshold_block = None

    try:
        while True:
            now_ist   = _ist_now()
            today_ist = now_ist.date()
            hm        = (now_ist.hour, now_ist.minute)
            tblock    = (today_ist, now_ist.minute // 10)

            if (8,0) <= hm < (8,30) and today_ist != _last_morning_date and _is_market_day(now_ist):
                logger.info("[SCHEDULER] Window: morning briefing")
                try:    send_morning_briefing(channel=channel)
                except Exception as exc: logger.error(f"[SCHEDULER] Morning briefing error: {exc}")
                _last_morning_date = today_ist

            if (14,0) <= hm < (14,30) and today_ist != _last_afternoon_date and _is_market_day(now_ist):
                logger.info("[SCHEDULER] Window: afternoon check")
                try:    send_afternoon_check(channel=channel)
                except Exception as exc: logger.error(f"[SCHEDULER] Afternoon check error: {exc}")
                _last_afternoon_date = today_ist

            if _is_market_day(now_ist) and tblock != _last_threshold_block:
                try:    check_price_threshold(channel=channel)
                except Exception as exc: logger.error(f"[SCHEDULER] Threshold check error: {exc}")
                _last_threshold_block = tblock

            time.sleep(30)

    except KeyboardInterrupt:
        logger.info("Notifier stopped by user.")
