"""Strategy ranking service (Module 6).

Ranks evaluated candidate remediation strategies for a specific
accessibility issue or deterministic issue group of a completed scan.

Flow::

    Authenticated user
        -> scan_id
        -> ContextBuilderService.build_for_scan()   (ownership + COMPLETED)
        -> resolve target issue/group
        -> detect context factors from ContextDocument
        -> compute weights (baseline or contextual)
        -> rank strategies by weighted score
        -> generate explanations
        -> RankingBatch (metadata + ranked strategies)

Ranking is fully deterministic and does not call an LLM. The service
depends on the context builder protocol only — no database access beyond
what the context builder provides.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.context.interfaces import ContextBuilder
from app.context.models import ContextDocument, IssueContext, IssueGroup
from app.evaluations.models import StrategyEvaluation
from app.rankings.algorithms import (
    DEFAULT_WEIGHTS,
    apply_contextual_weights,
    detect_context_factors,
    rank_strategies,
    validate_weights,
)
from app.rankings.exceptions import (
    RankingEvaluationsNotFoundError,
    RankingTargetNotFoundError,
)
from app.rankings.models import (
    RankingBatch,
    RankingMode,
    RankingResult,
    RankingWeights,
    RANKING_VERSION,
)


class StrategyRankingService:
    """Rank supplied evaluated strategies for an owned scan target."""

    def __init__(
        self,
        context_builder: ContextBuilder,
    ) -> None:
        self._context_builder = context_builder

    async def rank_strategies(
        self,
        user_id: str,
        scan_id: str,
        *,
        issue_id: Optional[str] = None,
        group_id: Optional[str] = None,
        strategies: List,  # List[CandidateStrategy] — kept generic to avoid import cycle
        evaluations: List[StrategyEvaluation],
        mode: RankingMode = RankingMode.CONTEXTUAL,
    ) -> RankingBatch:
        """Rank the supplied strategies using the given evaluation results.

        :raises ScanNotFoundError: missing or foreign scan (404-safe).
        :raises ContextUnavailableError: the scan has not completed (409).
        :raises RankingTargetNotFoundError: unknown issue/group (404).
        :raises RankingEvaluationsNotFoundError: no evaluations supplied (409).
        """
        context = await self._context_builder.build_for_scan(user_id, scan_id)
        target = self._resolve_target(context, issue_id=issue_id, group_id=group_id)

        if not evaluations:
            raise RankingEvaluationsNotFoundError(
                "No evaluations were supplied. Evaluate strategies before ranking."
            )

        # Match evaluations to strategies.
        strategy_ids = {s.strategy_id for s in strategies}
        matched = [e for e in evaluations if e.strategy_id in strategy_ids]
        if not matched:
            raise RankingEvaluationsNotFoundError(
                "None of the supplied evaluations match the provided strategies."
            )

        # Detect context factors.
        primary_issue = self._get_primary_issue(context, target)
        factors = detect_context_factors(context, primary_issue)

        # Compute weights.
        if mode == RankingMode.CONTEXTUAL:
            weights = apply_contextual_weights(DEFAULT_WEIGHTS, factors)
        else:
            weights = DEFAULT_WEIGHTS

        # Rank.
        primary_issue_id = target.get("issue_id") or (
            target["issues"][0].issue_id if target["issues"] else ""
        )
        ranked = rank_strategies(
            matched, weights, factors, mode.value
        )

        return RankingBatch(
            scan_id=scan_id,
            issue_id=primary_issue_id,
            group_id=target.get("group_id"),
            context_version=context.context_version,
            ranking_version=RANKING_VERSION,
            ranking_method=mode.value,
            weights_used=weights,
            context_factors=factors,
            ranked_strategies=ranked,
            generated_at=datetime.now(timezone.utc),
        )

    # --- target resolution ---------------------------------------------------

    @staticmethod
    def _resolve_target(
        context: ContextDocument,
        *,
        issue_id: Optional[str],
        group_id: Optional[str],
    ) -> dict:
        """Resolve and validate the target issue/group, returning a dict
        with the resolved information."""
        if issue_id and group_id:
            issue = _find_issue(context, issue_id)
            group = _find_group(context, group_id)
            if issue.issue_id not in group.issue_ids:
                raise RankingTargetNotFoundError(
                    "The issue does not belong to the selected group."
                )
            members = [i for i in context.issues if i.issue_id in group.issue_ids]
            return {
                "target_type": "group",
                "issue_id": issue_id,
                "group_id": group_id,
                "issues": members,
            }

        if issue_id:
            issue = _find_issue(context, issue_id)
            return {
                "target_type": "issue",
                "issue_id": issue_id,
                "issues": [issue],
            }

        if group_id:
            group = _find_group(context, group_id)
            members = [i for i in context.issues if i.issue_id in group.issue_ids]
            return {
                "target_type": "group",
                "group_id": group_id,
                "issues": members,
            }

        raise RankingTargetNotFoundError(
            "Provide an issue_id or group_id to rank strategies for."
        )

    @staticmethod
    def _get_primary_issue(
        context: ContextDocument,
        target: dict,
    ) -> IssueContext:
        """Get the primary issue from the resolved target."""
        issues = target.get("issues", [])
        if not issues:
            raise RankingTargetNotFoundError(
                "No issues found for the selected target."
            )
        return issues[0]


def _find_issue(context: ContextDocument, issue_id: str) -> IssueContext:
    for issue in context.issues:
        if issue.issue_id == issue_id:
            return issue
    raise RankingTargetNotFoundError("The issue was not found for this scan.")


def _find_group(context: ContextDocument, group_id: str) -> IssueGroup:
    for group in context.groups:
        if group.group_id == group_id:
            return group
    raise RankingTargetNotFoundError("The group was not found for this scan.")
