"""Shared implementation for providers exposing an OpenAI-compatible chat/completions endpoint."""
from __future__ import annotations

import requests

from .base import LLMAnswer, LLMClient, LLMRequestError, redact_secrets, request_with_retry


class OpenAICompatibleClient(LLMClient):
    api_url: str = ""

    def ask(self, query: str) -> LLMAnswer:
        key = self.require_key()
        try:
            resp = request_with_retry(
                "POST",
                self.api_url,
                headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                json={"model": self.model, "messages": [{"role": "user", "content": query}]},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMRequestError(f"{self.provider} request failed: {redact_secrets(str(exc))}") from exc

        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return LLMAnswer(provider=self.provider, model=self.model, query=query, text=text, raw=data)
