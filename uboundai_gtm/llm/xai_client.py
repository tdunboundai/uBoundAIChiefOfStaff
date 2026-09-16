from __future__ import annotations

from ._openai_compatible import OpenAICompatibleClient


class XAIClient(OpenAICompatibleClient):
    provider = "grok"
    default_model = "grok-4"
    api_url = "https://api.x.ai/v1/chat/completions"
