"""Strategy generation providers.

- :class:`OpenAIStrategyProvider` — any OpenAI-compatible chat-completions
  endpoint (OpenAI, Azure OpenAI, local gateways) via ``LLM_BASE_URL``.
- :class:`MockStrategyProvider` — a deterministic, clearly-labeled provider
  for tests and demonstrations; it never pretends to be a real LLM.

:func:`create_provider` dispatches on ``LLM_PROVIDER`` and fails gracefully
(503) when the ``openai`` provider is requested without an API key — the app
never silently substitutes a fake generator.
"""

from app.core.config import Settings
from app.strategies.exceptions import StrategyConfigurationError
from app.strategies.interfaces import StrategyGenerationProvider
from app.strategies.providers.mock import MockStrategyProvider
from app.strategies.providers.openai import OpenAIStrategyProvider

__all__ = [
    "OpenAIStrategyProvider",
    "MockStrategyProvider",
    "create_provider",
]


def create_provider(settings: Settings) -> StrategyGenerationProvider:
    """Resolve the configured strategy generation provider.

    :raises StrategyConfigurationError: unknown provider, or ``openai``
        selected without ``LLM_API_KEY`` (503 — never a fake fallback).
    """
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "mock":
        return MockStrategyProvider(settings)
    if provider == "openai":
        if not settings.llm_api_key:
            raise StrategyConfigurationError(
                "LLM_PROVIDER is 'openai' but LLM_API_KEY is not configured. "
                "Set LLM_API_KEY (or LLM_PROVIDER=mock for the deterministic "
                "demonstration provider)."
            )
        return OpenAIStrategyProvider(settings)
    raise StrategyConfigurationError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'openai' or 'mock'."
    )
