"""Strategy generation domain (Module 4).

Public surface: the :class:`StrategyGenerationService`, the
:class:`CandidateStrategy` / :class:`StrategyGeneration` models, and the
provider abstraction. The API layer depends only on these — never on a
concrete LLM provider.
"""

from app.strategies.models import (
    CandidateStrategy,
    StrategyGeneration,
    StrategyGenerationMetadata,
)
from app.strategies.services import StrategyGenerationService

__all__ = [
    "CandidateStrategy",
    "StrategyGeneration",
    "StrategyGenerationMetadata",
    "StrategyGenerationService",
]
