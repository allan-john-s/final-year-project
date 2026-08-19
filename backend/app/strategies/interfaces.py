"""Strategy generation provider contract.

The :class:`StrategyGenerationService` depends on this protocol — never on a
concrete provider — so new providers (OpenAI, Azure OpenAI, local models,
research gateways) can be added without touching the service or the API.
"""

from typing import List, Protocol

from app.strategies.models import CandidateStrategy, StrategyGenerationRequest


class StrategyGenerationProvider(Protocol):
    """Generates candidate strategies from a versioned prompt request."""

    name: str

    async def generate(
        self, request: StrategyGenerationRequest
    ) -> List[CandidateStrategy]:
        """Return validated candidate strategies.

        :raises StrategyProviderError: transport/upstream failure (timeout,
            rate limit, network).
        :raises StrategyOutputError: the response could not be parsed or
            validated against :class:`CandidateStrategy`.
        """
        ...
