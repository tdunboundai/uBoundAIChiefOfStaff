from __future__ import annotations

import requests

from .base import LLMAnswer, LLMClient, LLMRequestError, request_with_retry

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicClient(LLMClient):
    provider = "claude"
    default_model = "claude-sonnet-5"

    def ask(self, query: str) -> LLMAnswer:
        key = self.require_key()
        try:
            resp = request_with_retry(
                "POST",
                API_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": query}],
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMRequestError(f"Anthropic request failed: {exc}") from exc

        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        return LLMAnswer(provider=self.provider, model=self.model, query=query, text=text, raw=data)
