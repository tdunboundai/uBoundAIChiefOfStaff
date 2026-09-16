from __future__ import annotations

import requests

from .base import LLMAnswer, LLMClient, LLMRequestError

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GoogleClient(LLMClient):
    provider = "gemini"
    default_model = "gemini-2.5-pro"

    def ask(self, query: str) -> LLMAnswer:
        key = self.require_key()
        url = API_URL_TEMPLATE.format(model=self.model)
        try:
            resp = requests.post(
                url,
                headers={"content-type": "application/json"},
                params={"key": key},
                json={"contents": [{"parts": [{"text": query}]}]},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMRequestError(f"Google request failed: {exc}") from exc

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            text = ""
        return LLMAnswer(provider=self.provider, model=self.model, query=query, text=text, raw=data)
