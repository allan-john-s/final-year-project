"""Strategy dependencies for route handlers.

- :func:`get_strategy_provider` — resolves the configured LLM provider via
  the factory (swappable in tests; ``LLM_PROVIDER=mock`` for demos).
- :func:`get_strategy_service` — the generation service built on the context
  builder + provider + settings.
"""

from typing import Annotated

from fastapi import Depends

from app.context.interfaces import ContextBuilder
from app.core.config import Settings, get_settings
from app.dependencies.context import get_context_service
from app.strategies.interfaces import StrategyGenerationProvider
from app.strategies.providers import create_provider
from app.strategies.services import StrategyGenerationService
from app.context.services import ContextBuilderService


def get_strategy_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StrategyGenerationProvider:
    """Resolve the configured strategy generation provider."""
    return create_provider(settings)


def get_strategy_service(
    context_builder: Annotated[ContextBuilderService, Depends(get_context_service)],
    provider: Annotated[StrategyGenerationProvider, Depends(get_strategy_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StrategyGenerationService:
    """Resolve the strategy generation service."""
    return StrategyGenerationService(
        context_builder=context_builder,
        provider=provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
