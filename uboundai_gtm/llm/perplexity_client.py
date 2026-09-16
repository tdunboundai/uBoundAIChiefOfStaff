from __future__ import annotations

from ._openai_compatible import OpenAICompatibleClient


class PerplexityClient(OpenAICompatibleClient):
    provider = "perplexity"
    default_model = "sonar-pro"
    api_url = "https://api.perplexity.ai/chat/completions"
