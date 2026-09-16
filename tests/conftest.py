from __future__ import annotations

import pytest

from uboundai_gtm.llm.base import LLMAnswer, LLMClient


class FakeLLMClient(LLMClient):
    """Deterministic stand-in for a real provider: returns a fixed response
    (or raises a given exception) for every `.ask()` call, so bot logic can
    be tested without network access."""

    def __init__(self, provider: str, response: str | Exception = "", model: str = "fake-model"):
        super().__init__(api_key="fake-key", model=model)
        self.provider = provider
        self._response = response
        self.calls: list[str] = []

    def ask(self, query: str) -> LLMAnswer:
        self.calls.append(query)
        if isinstance(self._response, Exception):
            raise self._response
        return LLMAnswer(provider=self.provider, model=self.model, query=query, text=self._response)


@pytest.fixture
def fake_client():
    return FakeLLMClient
