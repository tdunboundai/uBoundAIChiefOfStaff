"""Shared interface every LLM provider client implements."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class MissingAPIKeyError(RuntimeError):
    """Raised at call time (not import time) when a provider's API key is absent."""


class LLMRequestError(RuntimeError):
    """Raised when a provider call fails (network error, non-2xx response, bad payload)."""


def request_with_retry(
    method: str,
    url: str,
    *,
    request_fn: Callable[..., requests.Response] = requests.request,
    max_retries: int = 2,
    backoff_seconds: float = 2.0,
    **kwargs,
) -> requests.Response:
    """Every provider's free/low tier returns 429 (rate limited) or a 5xx
    under normal load — e.g. Gemini's own "This model is currently
    experiencing high demand" 503 — so a bare single-shot call fails far
    more often than the underlying service actually is. Retries those
    specific statuses with exponential backoff; anything else (4xx like a
    bad model name or bad auth) raises immediately since retrying won't help."""
    last_exc: requests.RequestException | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = request_fn(method, url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            time.sleep(backoff_seconds * (2**attempt))
            continue

        if resp.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
            time.sleep(backoff_seconds * (2**attempt))
            continue

        resp.raise_for_status()
        return resp
    raise last_exc  # pragma: no cover - unreachable, loop always returns or raises


@dataclass(frozen=True)
class LLMAnswer:
    provider: str
    model: str
    query: str
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Base class for a single provider. Subclasses implement `ask`."""

    provider: str = "base"
    default_model: str = ""

    def __init__(self, api_key: str | None, model: str | None = None, timeout: float = 30.0):
        self.api_key = api_key
        self.model = model or self.default_model
        self.timeout = timeout

    def require_key(self) -> str:
        if not self.api_key:
            raise MissingAPIKeyError(
                f"{self.provider} client has no API key configured. "
                f"Set the corresponding environment variable (see .env.example)."
            )
        return self.api_key

    def ask(self, query: str) -> LLMAnswer:  # pragma: no cover - interface
        raise NotImplementedError
