"""Shared FastAPI dependencies (optional API-key gate)."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Reject requests when ``REHEALTH_API_KEY`` is configured.

    If the variable is unset the API runs in open development mode.  Never
    expose that mode publicly: the endpoints can trigger one LLM call per
    simulated day.
    """
    expected = os.getenv("REHEALTH_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key header",
        )
