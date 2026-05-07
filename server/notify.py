"""Firebase Cloud Messaging (HTTP v1) helper.

Used by the FastAPI server (and optionally by the automations themselves via
``lib/fcm.py``) to push topic notifications to the Android app.

Configure via env:
    FCM_PROJECT_ID         — GCP project id (e.g. ``my-app-7e2``)
    FCM_CREDENTIALS_JSON   — path to a service-account JSON, OR
    FCM_CREDENTIALS_INLINE — service-account JSON content (string)

If credentials are absent the helper silently no-ops so dev environments
don't break.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger("server.fcm")

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SEND_URL_TMPL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

_token_cache: dict[str, Any] = {"value": None, "exp": 0.0}
_token_lock = threading.Lock()


def _credentials() -> dict | None:
    inline = os.environ.get("FCM_CREDENTIALS_INLINE", "").strip()
    if inline:
        try:
            return json.loads(inline)
        except Exception as exc:
            logger.warning("FCM_CREDENTIALS_INLINE is not valid JSON: %s", exc)
            return None
    path = os.environ.get("FCM_CREDENTIALS_JSON", "").strip()
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to read FCM credentials %s: %s", path, exc)
            return None
    return None


def _access_token() -> str | None:
    """Fetches an OAuth2 access token, cached until shortly before expiry."""
    now = time.time()
    with _token_lock:
        if _token_cache["value"] and _token_cache["exp"] > now + 30:
            return _token_cache["value"]

        creds = _credentials()
        if not creds:
            return None
        try:
            # Lazy import to keep server light if FCM is not used.
            import jwt  # type: ignore  # PyJWT
        except Exception:
            logger.warning("PyJWT not installed; cannot mint FCM tokens")
            return None

        iat = int(now)
        payload = {
            "iss": creds["client_email"],
            "scope": _FCM_SCOPE,
            "aud": _TOKEN_URL,
            "iat": iat,
            "exp": iat + 3600,
        }
        try:
            assertion = jwt.encode(payload, creds["private_key"], algorithm="RS256")
        except Exception as exc:
            logger.warning("Failed to sign FCM JWT: %s", exc)
            return None

        try:
            r = requests.post(
                _TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=15,
            )
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            logger.warning("FCM token exchange failed: %s", exc)
            return None

        token = body.get("access_token")
        if not token:
            return None
        _token_cache["value"] = token
        _token_cache["exp"] = now + float(body.get("expires_in", 3600))
        return token


def send_topic(topic: str, *, title: str, body: str, data: dict[str, str] | None = None) -> bool:
    """Sends a push notification to ``/topics/<topic>``. Returns success."""
    creds = _credentials()
    if not creds:
        logger.info("FCM credentials not configured; skipping push to %s", topic)
        return False
    project_id = os.environ.get("FCM_PROJECT_ID") or creds.get("project_id")
    if not project_id:
        logger.warning("FCM_PROJECT_ID not set; cannot push")
        return False
    token = _access_token()
    if not token:
        return False

    payload = {
        "message": {
            "topic": topic,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
            "android": {"priority": "HIGH"},
        }
    }
    try:
        r = requests.post(
            _SEND_URL_TMPL.format(project_id=project_id),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=15,
        )
        if r.status_code >= 300:
            logger.warning("FCM send failed (%s): %s", r.status_code, r.text[:300])
            return False
        return True
    except Exception as exc:
        logger.warning("FCM send exception: %s", exc)
        return False
