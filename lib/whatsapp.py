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
        size = os.path.getsize(image_path)
        logger.info(
            f"Sending image to {phone} via Green API "
            f"({os.path.basename(image_path)}, {size/1024:.0f} KB, "
            f"caption {len(caption or '')} chars) …"
        )
        with open(image_path, "rb") as fh:
            resp = requests.post(
                url,
                data={"chatId": f"{phone}@c.us", "caption": caption},
                files={"file": (os.path.basename(image_path), fh, "image/png")},
                timeout=60,
                proxies=proxies or {},
            )
        if resp.status_code >= 400:
            logger.error(
                f"Green API HTTP {resp.status_code} on sendFileByUpload: "
                f"{resp.text[:500]}"
            )
            return False
        result = resp.json()
        if result.get("idMessage"):
            logger.info(f"Image sent (id: {result['idMessage']}).")
            return True
        logger.error(f"Green API image response: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send image: {exc}")
        return False


_MIME_BY_EXT = {
    ".pdf":  "application/pdf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".csv":  "text/csv",
    ".txt":  "text/plain",
}


def send_document(
    phone: str,
    file_path: str,
    caption: str,
    instance: str,
    token: str,
    api_url: str,
    proxies: dict | None = None,
) -> bool:
    """Upload an arbitrary document (PDF etc.) via Green API sendFileByUpload."""
    if not instance or not token:
        logger.error("Green API credentials missing - cannot send document.")
        return False
    if not os.path.exists(file_path):
        logger.error(f"Document not found: {file_path}")
        return False
    ext  = os.path.splitext(file_path)[1].lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    url  = f"{api_url}/waInstance{instance}/sendFileByUpload/{token}"
    try:
        with open(file_path, "rb") as fh:
            resp = requests.post(
                url,
                data={"chatId": f"{phone}@c.us", "caption": caption},
                files={"file": (os.path.basename(file_path), fh, mime)},
                timeout=120,
                proxies=proxies or {},
            )
        resp.raise_for_status()
        result = resp.json()
        if result.get("idMessage"):
            logger.info(f"Document sent (id: {result['idMessage']}): "
                        f"{os.path.basename(file_path)}")
            return True
        logger.error(f"Green API document response: {result}")
        return False
    except Exception as exc:
        logger.error(f"Failed to send document: {exc}")
        return False
