"""Shared LLM client — all agents use the same DeepSeek connection."""

from openai import AsyncOpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Return a shared AsyncOpenAI client for DeepSeek."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def get_model() -> str:
    """Return the configured model name."""
    return DEEPSEEK_MODEL
