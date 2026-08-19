"""Strategy generation service (Module 4).

Turns a completed scan's :class:`ContextDocument` into 2–5 distinct
*candidate* remediation strategies for one selected issue or deterministic
issue group.

Flow::

    Authenticated user
        -> scan_id
        -> ContextBuilderService.build_for_scan()   (ownership + COMPLETED)
        -> resolve target issue/group
        -> versioned prompt (trusted instructions vs. untrusted context)
        -> StrategyGenerationProvider.generate()
        -> validation (count, uniqueness, schema)
        -> StrategyGeneration (metadata + CandidateStrategy list)

The service never touches Supabase directly — it consumes the context
builder (which reads through the existing repositories) and the provider
protocol. It is fully testable with in-memory fakes and the mock provider.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.context.interfaces import ContextBuilder
from app.context.models import ContextDocument, IssueGroup, IssueContext
from app.strategies.exceptions import (
    StrategyOutputError,
    StrategyTargetNotFoundError,
)
from app.strategies.interfaces import StrategyGenerationProvider
from app.strategies.models import (
    CandidateStrategy,
    StrategyGeneration,
    StrategyGenerationMetadata,
    StrategyGenerationRequest,
    StrategyTarget,
)
from app.strategies.prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt


class StrategyGenerationService:
    """Generate validated candidate strategies for an owned scan target."""

    def __init__(
        self,
        context_builder: ContextBuilder,
        provider: StrategyGenerationProvider,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._context_builder = context_builder
        self._provider = provider
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def generate_strategies(
        self,
        user_id: str,
        scan_id: str,
        *,
        issue_id: Optional[str] = None,
        group_id: Optional[str] = None,
        strategy_count: int = 3,
    ) -> StrategyGeneration:
        """Generate strategies for one issue or group of ``scan_id``.

        :raises ScanNotFoundError: missing or foreign scan (404-safe).
        :raises ContextUnavailableError: the scan has not completed (409).
        :raises StrategyTargetNotFoundError: unknown issue/group (404).
        :raises StrategyConfigurationError / StrategyProviderError /
            StrategyOutputError: provider problems (503/502).
        """
        context = await self._context_builder.build_for_scan(user_id, scan_id)
        target = self._resolve_target(context, issue_id=issue_id, group_id=group_id)

        system_prompt = build_system_prompt(strategy_count)
        user_prompt = build_user_prompt(context, target, strategy_count)
        request = StrategyGenerationRequest(
            prompt_version=PROMPT_VERSION,
            context_version=context.context_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            target=target,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            strategy_count=strategy_count,
        )

        strategies = await self._provider.generate(request)
        strategies = self._finalize(strategies, context, target, strategy_count)

        metadata = StrategyGenerationMetadata(
            scan_id=scan_id,
            target_type=target.target_type,
            issue_id=target.issue_id,
            group_id=target.group_id,
            context_version=context.context_version,
            prompt_version=PROMPT_VERSION,
            provider=self._provider.name,
            model=self._model,
            temperature=self._temperature,
            strategy_count=len(strategies),
            generated_at=datetime.now(timezone.utc),
        )
        return StrategyGeneration(metadata=metadata, strategies=strategies)

    # --- target resolution ---------------------------------------------------

    @staticmethod
    def _resolve_target(
        context: ContextDocument,
        *,
        issue_id: Optional[str],
        group_id: Optional[str],
    ) -> StrategyTarget:
        if issue_id and group_id:
            issue = _find_issue(context, issue_id)
            group = _find_group(context, group_id)
            if issue.issue_id not in group.issue_ids:
                raise StrategyTargetNotFoundError(
                    "The issue does not belong to the selected group."
                )
            members = [i for i in context.issues if i.issue_id in group.issue_ids]
            return StrategyTarget(
                target_type="group", issue_id=issue_id, group_id=group_id,
                issues=members,
            )

        if issue_id:
            issue = _find_issue(context, issue_id)
            return StrategyTarget(
                target_type="issue", issue_id=issue_id, issues=[issue]
            )

        if group_id:
            group = _find_group(context, group_id)
            members = [i for i in context.issues if i.issue_id in group.issue_ids]
            return StrategyTarget(
                target_type="group", group_id=group_id, issues=members
            )

        raise StrategyTargetNotFoundError(
            "Provide an issue_id or group_id to generate strategies for."
        )

    # --- validation ----------------------------------------------------------

    @staticmethod
    def _finalize(
        strategies: List[CandidateStrategy],
        context: ContextDocument,
        target: StrategyTarget,
        strategy_count: int,
    ) -> List[CandidateStrategy]:
        """Validate count/uniqueness and stamp traceability fields."""
        if len(strategies) < 2:
            raise StrategyOutputError(
                "The provider returned fewer than 2 strategies."
            )
        if len(strategies) > 5 or len(strategies) > strategy_count:
            raise StrategyOutputError(
                "The provider returned more strategies than requested."
            )

        ids = [s.strategy_id for s in strategies]
        if len(set(ids)) != len(ids):
            raise StrategyOutputError("The provider returned duplicate strategy ids.")

        titles = [s.title.strip().lower() for s in strategies]
        if len(set(titles)) != len(titles):
            raise StrategyOutputError(
                "The provider returned duplicate strategy titles."
            )

        primary_issue_id = target.issue_id or (
            target.issues[0].issue_id if target.issues else ""
        )
        reference = target.issue_id or target.group_id or primary_issue_id

        stamped: List[CandidateStrategy] = []
        for index, strategy in enumerate(strategies, start=1):
            stamped.append(
                strategy.model_copy(
                    update={
                        "strategy_index": index,
                        "issue_id": primary_issue_id,
                        "group_id": target.group_id,
                        "context_version": context.context_version,
                        "evidence_reference": reference,
                    }
                )
            )
        return stamped


def _find_issue(context: ContextDocument, issue_id: str) -> IssueContext:
    for issue in context.issues:
        if issue.issue_id == issue_id:
            return issue
    raise StrategyTargetNotFoundError("The issue was not found for this scan.")


def _find_group(context: ContextDocument, group_id: str) -> IssueGroup:
    for group in context.groups:
        if group.group_id == group_id:
            return group
    raise StrategyTargetNotFoundError("The group was not found for this scan.")
