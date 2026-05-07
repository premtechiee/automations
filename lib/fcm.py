"""Thin FCM client used by automations to push notifications to the Android app.

Decoupled from the FastAPI server so scripts can import without server deps.
Reads service-account credentials from env (see ``server/notify.py`` for the
full env var contract). Silently no-ops if credentials are absent so the
existing automations don't fail when Firebase isn't configured.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("lib.fcm")


def is_configured() -> bool:
    return bool(
        os.environ.get("FCM_CREDENTIALS_JSON")
        or os.environ.get("FCM_CREDENTIALS_INLINE")
    )


def notify_app(
    kind: str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """Send a push to the topic associated with ``kind``.

    ``kind`` ∈ {``stock``, ``gold``, ``paper``, ``live``}. Returns ``True`` on
    success, ``False`` if FCM is not configured or the send failed (always
    safe to ignore).
    """
    topic = {
        "stock": "stock_reports",
        "gold":  "gold_updates",
        "paper": "paper_reports",
        "live":  "live_alerts",
    }.get(kind)
    if not topic:
        logger.warning("notify_app: unknown kind %r", kind)
        return False
    if not is_configured():
        return False
    try:
        # Lazy import — server.notify pulls in requests + jwt + threads.
        from server.notify import send_topic
    except Exception as exc:
        logger.info("notify_app: server.notify unavailable (%s)", exc)
        return False
    return send_topic(topic, title=title, body=body, data=data or {})
