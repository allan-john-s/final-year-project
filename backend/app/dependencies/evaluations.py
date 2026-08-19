"""Evaluation dependencies for route handlers.

- :func:`get_evaluation_provider` — resolves the configured evaluator via
  the factory (swappable in tests; ``LLM_PROVIDER=mock`` for demos).
- :func:`get_evaluation_service` — the evaluation service built on the
  context builder + provider + settings.
"""

from typing import Annotated

from fastapi import Depends

from app.context.services import ContextBuilderService
from app.core.config import Settings, get_settings
from app.dependencies.context import get_context_service
from app.evaluations.interfaces import StrategyEvaluationProvider
from app.evaluations.providers import create_provider
from app.evaluations.services import StrategyEvaluationService


def get_evaluation_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StrategyEvaluationProvider:
    """Resolve the configured strategy evaluation provider."""
    return create_provider(settings)


def get_evaluation_service(
    context_builder: Annotated[ContextBuilderService, Depends(get_context_service)],
    provider: Annotated[StrategyEvaluationProvider, Depends(get_evaluation_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StrategyEvaluationService:
    """Resolve the strategy evaluation service."""
    return StrategyEvaluationService(
        context_builder=context_builder,
        provider=provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
