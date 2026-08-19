"""Ranking dependencies for route handlers (Module 6).

- :func:`get_ranking_service` — the ranking service built on the context
  builder. The ranking service is stateless and deterministic — no LLM
  provider is needed.
"""

from typing import Annotated

from fastapi import Depends

from app.context.services import ContextBuilderService
from app.dependencies.context import get_context_service
from app.rankings.services import StrategyRankingService


def get_ranking_service(
    context_builder: Annotated[ContextBuilderService, Depends(get_context_service)],
) -> StrategyRankingService:
    """Resolve the strategy ranking service."""
    return StrategyRankingService(context_builder=context_builder)
