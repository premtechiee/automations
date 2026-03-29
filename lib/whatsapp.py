"""
shared/whatsapp.py
==================
Green API WhatsApp sender — shared by all automations that need messaging.

Credentials are passed in at call time (not hard-coded here) so each
automation can supply its own instance/token from its own config.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)


def send_message(
    phone: str,
    message: str,
    instance: str,
    token: str,
    api_url: str,
    proxies: dict | None = None,
) -> bool:
    """Send a plain-text WhatsApp message via Green API."""
    if not instance or not token:
        logger.error("GREEN_API_INSTANCE or GREEN_API_TOKEN is empty.")
        return False

    url = f"{api_url}/waInstance{instance}/sendMessage/{token}"
    payload = {"chatId": f"{phone}@c.us", "message": message}
    try:
        logger.info(f"Sending message to {phone} via Green API …")
        resp = requests.post(url, json=payload, timeout=30, proxies=proxies or {})
        resp.raise_for_status()
        result = resp.json()
        if result.get("idMessage"):
            logger.info(f"Message sent (id: {result['idMessage']}).")
            return True
        logger.error(f"Green API unexpected response: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send WhatsApp message: {exc}")
        return False


def send_image(
    phone: str,
    image_path: str,
    caption: str,
    instance: str,
    token: str,
    api_url: str,
    proxies: dict | None = None,
) -> bool:
    """Upload an image to WhatsApp via Green API sendFileByUpload."""
    if not instance or not token:
        logger.error("Green API credentials missing — cannot send image.")
        return False

    url = f"{api_url}/waInstance{instance}/sendFileByUpload/{token}"
    try:
        with open(image_path, "rb") as fh:
            resp = requests.post(
                url,
                data={"chatId": f"{phone}@c.us", "caption": caption},
                files={"file": (os.path.basename(image_path), fh, "image/png")},
                timeout=60,
                proxies=proxies or {},
            )
        resp.raise_for_status()
        result = resp.json()
        if result.get("idMessage"):
            logger.info(f"Image sent (id: {result['idMessage']}).")
            return True
        logger.error(f"Green API image response: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send image: {exc}")
        return False
