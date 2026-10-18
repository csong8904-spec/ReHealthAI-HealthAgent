"""Defensive wrapper around the DeepSeek chat-completions API.

Design goals:

* importing this module must never require a network call or an API key;
* a failing / rate-limited / non-JSON response must never corrupt a simulation
  (the caller falls back to the rule-based adherence model);
* the call budget is bounded, because one simulation makes one call per
  simulated day.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

SYSTEM_PROMPT = (
    "You are a behavioural-science simulation component. You predict whether a "
    "simulated patient will adhere to a health intervention on a single day. "
    "You always reply with a single JSON object and nothing else."
)


class LLMUnavailable(RuntimeError):
    """Raised when the LLM backend cannot be used."""


def _extract_json(text: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from a model response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # drop ```json / ``` fences
        cleaned = cleaned.split("```", 2)
        cleaned = cleaned[1] if len(cleaned) > 1 else text
        cleaned = cleaned.removeprefix("json").strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMUnavailable(f"model did not return JSON: {text[:200]!r}")
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"model returned malformed JSON: {text[:200]!r}") from exc
    if not isinstance(payload, dict):
        raise LLMUnavailable(f"expected a JSON object, got {type(payload).__name__}")
    return payload


class LLMClient:
    """Minimal, retrying JSON client.

    Args:
        api_key: DeepSeek key.  Defaults to ``$DEEPSEEK_API_KEY``.
        base_url: API base URL.  Defaults to ``$DEEPSEEK_BASE_URL``.
        model: Chat model name.  Defaults to ``$DEEPSEEK_MODEL``.
        timeout: Per-request timeout in seconds.
        max_retries: Retries after the first failed attempt.
        max_calls: Hard budget for a single simulation run (``None`` = no cap).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff: float = 1.5,
        max_calls: Optional[int] = None,
    ) -> None:
        try:  # python-dotenv is optional at runtime
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:  # pragma: no cover - optional dependency
            pass

        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.backoff = float(backoff)
        self.max_calls = max_calls

        self._client: Any = None
        self._calls = 0
        #: Cumulative token usage reported by the backend (for cost tracking).
        self.usage_totals: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    # ------------------------------------------------------------------ info
    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def calls(self) -> int:
        """Number of (attempted) API calls, including retries."""
        return self._calls

    def usage_summary(self) -> Dict[str, int]:
        """Return cumulative token usage for this client."""
        return dict(self.usage_totals)

    def describe(self) -> str:
        if not self.available:
            return "LLM disabled (DEEPSEEK_API_KEY not set) -> rule-based mode"
        return f"LLM enabled (model={self.model}, base_url={self.base_url})"

    # --------------------------------------------------------------- internals
    def _ensure_client(self):
        if not self.available:
            raise LLMUnavailable("DEEPSEEK_API_KEY is not set")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMUnavailable(
                    "the 'openai' package is not installed; run `pip install -e .`"
                ) from exc
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,  # retries are handled here
            )
        return self._client

    # ------------------------------------------------------------------- call
    def complete_json(
        self,
        prompt: str,
        max_tokens: int = 700,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Return a parsed JSON object, retrying transient failures."""
        if self.max_calls is not None and self._calls >= self.max_calls:
            raise LLMUnavailable(f"LLM call budget exhausted ({self.max_calls} calls)")

        client = self._ensure_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                self._calls += 1
                response = client.chat.completions.create(**kwargs)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    for field in self.usage_totals:
                        value = getattr(usage, field, None)
                        if isinstance(value, int):
                            self.usage_totals[field] += value
                text = (response.choices[0].message.content or "").strip()
                return _extract_json(text)
            except Exception as exc:  # noqa: BLE001 - deliberately broad
                last_error = exc
                message = str(exc).lower()
                # Some deployments reject response_format; retry without it.
                if "response_format" in message and "response_format" in kwargs:
                    kwargs.pop("response_format", None)
                    logger.warning("backend rejected response_format; retrying without it")
                    continue
                logger.warning(
                    "LLM call failed (%s/%s): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff ** attempt)
        raise LLMUnavailable(f"LLM call failed after retries: {last_error}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "LLMClient":
        """Build a client from environment variables with optional overrides."""
        return cls(**overrides)
