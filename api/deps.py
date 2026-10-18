"""Shared FastAPI dependencies (optional API-key gate)."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


def require_api_key(
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
        description=(
            "Required when REHEALTH_API_KEY is configured. / "
            "配置了 REHEALTH_API_KEY 时必须提供。"
        ),
    ),
) -> None:
    """Reject requests when ``REHEALTH_API_KEY`` is configured.

    If the variable is unset the API runs in open development mode. Never expose
    that mode publicly: the endpoints can trigger one LLM call per simulated day.

    当设置了 ``REHEALTH_API_KEY`` 时校验请求头；未设置时以开放的开发模式运行。
    不要把开发模式暴露到公网：接口可能按模拟天数触发 LLM 调用。
    """
    expected = os.getenv("REHEALTH_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-API-Key header / 缺少或错误的 X-API-Key 请求头",
        )
