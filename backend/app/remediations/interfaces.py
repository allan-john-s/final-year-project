"""Remediation provider contract.

The :class:`RemediationService` depends on this protocol — never on a
concrete provider — so new providers (OpenAI, Azure, local models,
research gateways) can be added without touching the service or the API.
"""

from typing import Protocol

from app.remediations.models import RemediationProposal


class RemediationProvider(Protocol):
    """Generates a structured remediation proposal for one accessibility issue."""

    name: str

    async def generate_proposal(
        self,
        *,
        scan_id: str,
        issue_id: str,
        strategy_id: str,
        rank: int,
        issue_description: str,
        strategy_title: str,
        strategy_summary: str,
        strategy_rationale: str,
        implementation_steps: list[str],
        element_html: str,
        element_selector: str,
        wcag_criteria: list[str],
    ) -> RemediationProposal:
        """Return a validated remediation proposal for the supplied issue/strategy.

        :raises RemediationProviderError: transport/upstream failure.
        :raises RemediationOutputError: the response could not be parsed.
        """
        ...
