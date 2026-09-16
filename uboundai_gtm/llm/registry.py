"""Factory that builds all 5 provider clients from environment variables."""
from __future__ import annotations

import os

from .anthropic_client import AnthropicClient
from .base import LLMClient
from .google_client import GoogleClient
from .openai_client import OpenAIClient
from .perplexity_client import PerplexityClient
from .xai_client import XAIClient

# provider name -> (client class, env var holding the API key, env var overriding the model)
_PROVIDERS: dict[str, tuple[type[LLMClient], str, str]] = {
    "claude": (AnthropicClient, "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    "chatgpt": (OpenAIClient, "OPENAI_API_KEY", "OPENAI_MODEL"),
    "gemini": (GoogleClient, "GOOGLE_API_KEY", "GOOGLE_MODEL"),
    "grok": (XAIClient, "XAI_API_KEY", "XAI_MODEL"),
    "perplexity": (PerplexityClient, "PERPLEXITY_API_KEY", "PERPLEXITY_MODEL"),
}

ALL_PROVIDERS = tuple(_PROVIDERS.keys())


def build_client(provider: str) -> LLMClient:
    """Build a single provider's client. The client works even without a key set;
    it only raises MissingAPIKeyError when `.ask()` is actually called."""
    try:
        cls, key_env, model_env = _PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unknown provider '{provider}'. Known: {', '.join(ALL_PROVIDERS)}") from exc
    return cls(api_key=os.environ.get(key_env), model=os.environ.get(model_env))


def build_all_clients() -> dict[str, LLMClient]:
    """Build every provider's client, keyed by provider name."""
    return {name: build_client(name) for name in _PROVIDERS}
