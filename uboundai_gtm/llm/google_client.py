from __future__ import annotations

import requests

from .base import LLMAnswer, LLMClient, LLMRequestError, request_with_retry

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GoogleClient(LLMClient):
    provider = "gemini"
    # gemini-2.5-pro was deprecated for new API keys (Google now points them at
    # gemini-3.1-pro-preview); gemini-2.5-flash is confirmed working and is the
    # free-tier-friendly choice. Override via the GOOGLE_MODEL env var.
    default_model = "gemini-2.5-flash"

    def ask(self, query: str) -> LLMAnswer:
        key = self.require_key()
        url = API_URL_TEMPLATE.format(model=self.model)
        try:
            resp = request_with_retry(
                "POST",
                url,
                headers={"content-type": "application/json"},
                params={"key": key},
                json={"contents": [{"parts": [{"text": query}]}]},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMRequestError(f"Google request failed: {exc}") from exc

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            text = ""
        return LLMAnswer(provider=self.provider, model=self.model, query=query, text=text, raw=data)
