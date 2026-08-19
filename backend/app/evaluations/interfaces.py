"""Evaluation provider contract.

The :class:`StrategyEvaluationService` depends on this protocol — never on a
concrete provider — so new evaluators (OpenAI, Azure OpenAI, local models,
research gateways) can be added without touching the service or the API.
"""

from typing import Protocol

from app.evaluations.models import EvaluationDraft, StrategyEvaluationRequest


class StrategyEvaluationProvider(Protocol):
    """Evaluates ONE candidate strategy against its accessibility context."""

    name: str

    async def evaluate(
        self, request: StrategyEvaluationRequest
    ) -> EvaluationDraft:
        """Return a validated evaluation draft for the supplied strategy.

        :raises EvaluationProviderError: transport/upstream failure (timeout,
            rate limit, network).
        :raises EvaluationOutputError: the response could not be parsed or
            validated against :class:`EvaluationDraft`.
        """
        ...
