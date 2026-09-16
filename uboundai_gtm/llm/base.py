"""Shared interface every LLM provider client implements."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class MissingAPIKeyError(RuntimeError):
    """Raised at call time (not import time) when a provider's API key is absent."""


class LLMRequestError(RuntimeError):
    """Raised when a provider call fails (network error, non-2xx response, bad payload)."""


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
