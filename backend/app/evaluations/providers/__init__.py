"""Evaluation providers.

- :class:`OpenAIEvaluationProvider` — any OpenAI-compatible chat-completions
  endpoint (OpenAI, Azure OpenAI, local gateways) via ``LLM_BASE_URL``.
- :class:`MockEvaluationProvider` — a deterministic, clearly-labeled
  evaluator for tests and demonstrations; it never pretends to be a real LLM.

:func:`create_provider` dispatches on ``LLM_PROVIDER`` (the same setting that
governs strategy generation) and fails gracefully (503) when the ``openai``
provider is requested without an API key — the app never silently substitutes
a fake evaluator.
"""

from app.core.config import Settings
from app.evaluations.exceptions import EvaluationConfigurationError
from app.evaluations.interfaces import StrategyEvaluationProvider
from app.evaluations.providers.mock import MockEvaluationProvider
from app.evaluations.providers.openai import OpenAIEvaluationProvider

__all__ = [
    "OpenAIEvaluationProvider",
    "MockEvaluationProvider",
    "create_provider",
]


def create_provider(settings: Settings) -> StrategyEvaluationProvider:
    """Resolve the configured strategy evaluation provider.

    :raises EvaluationConfigurationError: unknown provider, or ``openai``
        selected without ``LLM_API_KEY`` (503 — never a fake fallback).
    """
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "mock":
        return MockEvaluationProvider(settings)
    if provider == "openai":
        if not settings.llm_api_key:
            raise EvaluationConfigurationError(
                "LLM_PROVIDER is 'openai' but LLM_API_KEY is not configured. "
                "Set LLM_API_KEY (or LLM_PROVIDER=mock for the deterministic "
                "demonstration provider)."
            )
        return OpenAIEvaluationProvider(settings)
    raise EvaluationConfigurationError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'openai' or 'mock'."
    )
