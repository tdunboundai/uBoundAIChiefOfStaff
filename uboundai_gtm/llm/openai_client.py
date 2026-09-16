from __future__ import annotations

from ._openai_compatible import OpenAICompatibleClient


class OpenAIClient(OpenAICompatibleClient):
    provider = "chatgpt"
    default_model = "gpt-5"
    api_url = "https://api.openai.com/v1/chat/completions"
