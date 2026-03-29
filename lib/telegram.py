"""
lib/telegram.py
===============
Telegram Bot API sender - shared by all automations needing notifications.
api.telegram.org is whitelisted on PythonAnywhere free tier.

Setup:
  1. Message @BotFather on Telegram -> /newbot -> copy the token
  2. Message your bot once, then get your chat_id:
     https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env
"""

import logging
import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}"


def send_message(
    chat_id: str,
    message: str,
    bot_token: str,
    proxies: dict | None = None,
) -> bool:
    """Send a plain-text or MarkdownV2 message via Telegram Bot API."""
    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty.")
        return False
    url = f"{_API_BASE.format(token=bot_token)}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=30, proxies=proxies or {})
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok"):
            logger.info(f"Telegram message sent (msg_id: {result['result']['message_id']}).")
            return True
        logger.error(f"Telegram API error: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send Telegram message: {exc}")
        return False


def send_photo(
    chat_id: str,
    image_path: str,
    caption: str,
    bot_token: str,
    proxies: dict | None = None,
) -> bool:
    """Upload and send a photo via Telegram Bot API sendPhoto."""
    if not bot_token or not chat_id:
        logger.error("Telegram credentials missing - cannot send photo.")
        return False
    import os
    if not os.path.exists(image_path):
        logger.error(f"Image not found: {image_path}")
        return False
    url = f"{_API_BASE.format(token=bot_token)}/sendPhoto"
    try:
        with open(image_path, "rb") as img:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": img},
                timeout=60,
                proxies=proxies or {},
            )
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok"):
            logger.info("Telegram photo sent.")
            return True
        logger.error(f"Telegram photo API error: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send Telegram photo: {exc}")
        return False
