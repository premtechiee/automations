"""Bearer-token auth for the automations API.

Configure via ``APP_API_TOKEN`` env var. Requests must send::

    Authorization: Bearer <token>

If the env var is unset the server refuses to start (fail-closed).
"""
from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


def _expected_token() -> str:
    tok = os.environ.get("APP_API_TOKEN", "").strip()
    if not tok:
        raise RuntimeError(
            "APP_API_TOKEN env var is not set. Refusing to start an unauthenticated API."
        )
    return tok


def require_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency that validates the ``Authorization: Bearer …`` header."""
    expected = _expected_token()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.split(None, 1)[1].strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
