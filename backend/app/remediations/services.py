"""Remediation service (Module 7).

Generates structured remediation proposals for the recommended (top-ranked)
accessibility strategy. The service validates ownership, verifies the strategy
is the recommended one, and delegates proposal generation to the provider.

Flow::

    Authenticated user
        -> scan_id + issue_id + strategy_id
        -> ContextBuilderService.build_for_scan()   (ownership + COMPLETED)
        -> verify strategy is associated with issue
        -> verify strategy was ranked (via ranking algorithm)
        -> verify strategy is rank #1 (recommended)
        -> RemediationProvider.generate_proposal()
        -> RemediationProposal (PROPOSED status)

The proposal is a REVIEW-FIRST artifact — the developer decides whether
to accept and apply it. Module 7 does NOT automatically modify source code.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.context.interfaces import ContextBuilder
from app.context.models import ContextDocument, IssueContext
from app.evaluations.models import StrategyEvaluation
from app.rankings.algorithms import DEFAULT_WEIGHTS, detect_context_factors, rank_strategies
from app.rankings.models import RankingMode, RankedStrategy
from app.remediations.exceptions import (
    RemediationNotFoundError,
    RemediationOutputError,
    RemediationProviderError,
    RemediationStrategyNotRankedError,
    RemediationTargetNotFoundError,
)
from app.remediations.interfaces import RemediationProvider
from app.remediations.models import (
    RemediationProposal,
    RemediationStatus,
    REMEDIATION_VERSION,
    _VALID_TRANSITIONS,
    is_valid_transition,
)


class RemediationService:
    """Generate and manage remediation proposals for an owned scan target."""

    def __init__(
        self,
        context_builder: ContextBuilder,
        provider: RemediationProvider,
    ) -> None:
        self._context_builder = context_builder
        self._provider = provider

    async def generate_proposal(
        self,
        user_id: str,
        scan_id: str,
        *,
        issue_id: str,
        strategy_id: str,
        strategies: List,  # List[CandidateStrategy] — generic to avoid import cycle
        evaluations: List[StrategyEvaluation],
    ) -> RemediationProposal:
        """Generate a remediation proposal for the recommended strategy.

        :raises ScanNotFoundError: missing or foreign scan (404-safe).
        :raises ContextUnavailableError: the scan has not completed (409).
        :raises RemediationTargetNotFoundError: unknown issue (404).
        :raises RemediationStrategyNotRankedError: strategy not recommended (409).
        :raises RemediationProviderError: provider failure (502).
        :raises RemediationOutputError: invalid provider output (502).
        """
        context = await self._context_builder.build_for_scan(user_id, scan_id)
        target_issue = self._find_issue(context, issue_id)

        # Verify the strategy exists in the supplied list.
        strategy = None
        for s in strategies:
            if s.strategy_id == strategy_id:
                strategy = s
                break
        if strategy is None:
            raise RemediationTargetNotFoundError(
                "The strategy was not found in the supplied strategies."
            )

        # Verify the strategy belongs to the issue.
        if strategy.issue_id != issue_id:
            raise RemediationTargetNotFoundError(
                "The strategy does not belong to the specified issue."
            )

        # Verify the strategy was evaluated.
        evaluation = None
        for e in evaluations:
            if e.strategy_id == strategy_id:
                evaluation = e
                break
        if evaluation is None:
            raise RemediationTargetNotFoundError(
                "No evaluation found for the specified strategy."
            )

        # Rank to determine if this is the recommended (rank #1) strategy.
        matched_evals = [e for e in evaluations if e.strategy_id in {s.strategy_id for s in strategies}]
        if not matched_evals:
            raise RemediationTargetNotFoundError(
                "No matching evaluations found for the supplied strategies."
            )

        factors = detect_context_factors(context, target_issue)
        weights = DEFAULT_WEIGHTS  # Use baseline for ranking verification
        ranked = rank_strategies(matched_evals, weights, factors, RankingMode.BASELINE.value)

        # Find the rank of the requested strategy.
        strategy_rank = None
        for r in ranked:
            if r.strategy_id == strategy_id:
                strategy_rank = r.rank
                break

        if strategy_rank is None:
            raise RemediationStrategyNotRankedError(
                "The strategy was not found in the ranking."
            )

        if strategy_rank != 1:
            raise RemediationStrategyNotRankedError(
                f"The strategy is ranked #{strategy_rank}. Only the top-ranked "
                f"strategy (rank #1) can generate a remediation proposal."
            )

        # Generate the proposal through the provider.
        try:
            proposal = await self._provider.generate_proposal(
                scan_id=scan_id,
                issue_id=issue_id,
                strategy_id=strategy_id,
                rank=strategy_rank,
                issue_description=target_issue.rule.description or target_issue.rule.help,
                strategy_title=strategy.title,
                strategy_summary=strategy.summary,
                strategy_rationale=strategy.rationale,
                implementation_steps=strategy.implementation_steps,
                element_html=target_issue.element.html,
                element_selector=target_issue.element.selector,
                wcag_criteria=target_issue.wcag.criteria,
            )
        except Exception as exc:
            if isinstance(exc, (RemediationProviderError, RemediationOutputError)):
                raise
            raise RemediationProviderError(
                "The remediation provider failed. Please try again."
            ) from exc

        # Validate the proposal matches the request.
        if proposal.issue_id != issue_id or proposal.strategy_id != strategy_id:
            raise RemediationOutputError(
                "The provider returned a proposal for a different issue/strategy."
            )

        return proposal

    @staticmethod
    def _find_issue(context: ContextDocument, issue_id: str) -> IssueContext:
        """Find an issue by ID in the context."""
        for issue in context.issues:
            if issue.issue_id == issue_id:
                return issue
        raise RemediationTargetNotFoundError("The issue was not found for this scan.")

    @staticmethod
    def validate_status_transition(
        current: RemediationStatus,
        target: RemediationStatus,
    ) -> None:
        """Validate a status transition. Raises if invalid."""
        if not is_valid_transition(current, target):
            from app.remediations.exceptions import RemediationInvalidTransitionError
            raise RemediationInvalidTransitionError(
                f"Cannot transition from {current.value} to {target.value}. "
                f"Valid transitions from {current.value}: "
                f"{[t.value for t in _VALID_TRANSITIONS[current]]}"
            )
