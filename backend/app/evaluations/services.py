"""Strategy evaluation service (Module 5).

Evaluates EACH supplied candidate remediation strategy independently against
the accessibility context of a completed scan, producing a multidimensional
:class:`StrategyEvaluation` per strategy. No ranking, no total score, no
winner — the service only produces per-candidate evidence.

Flow::

    Authenticated user
        -> scan_id
        -> ContextBuilderService.build_for_scan()   (ownership + COMPLETED)
        -> resolve target issue/group
        -> validate every supplied strategy against the deterministic context
        -> per strategy: versioned evaluation prompt (trusted vs. untrusted)
        -> StrategyEvaluationProvider.evaluate()
        -> stamp traceability (scan/issue/group, versions, provider, model)
        -> EvaluationBatch (one independent evaluation per strategy)

Strategies are generated on demand and never persisted, so the service never
trusts client-supplied ids: each strategy object is re-validated against the
ContextDocument (issue/group membership, context version, evidence
reference). The service touches Supabase only through the context builder's
repositories and is fully testable with in-memory fakes + the mock provider.
"""

from datetime import datetime, timezone
from typing import List, Optional

from app.context.interfaces import ContextBuilder
from app.context.models import ContextDocument, IssueGroup, IssueContext
from app.evaluations.exceptions import (
    EvaluationOutputError,
    EvaluationStrategyInvalidError,
    EvaluationTargetNotFoundError,
)
from app.evaluations.interfaces import StrategyEvaluationProvider
from app.evaluations.models import (
    EVALUATION_VERSION,
    EvaluationBatch,
    EvaluationDraft,
    StrategyEvaluation,
    StrategyEvaluationRequest,
)
from app.evaluations.prompts import (
    EVALUATION_PROMPT_VERSION,
    build_evaluation_system_prompt,
    build_evaluation_user_prompt,
)
from app.strategies.models import CandidateStrategy, StrategyTarget


class StrategyEvaluationService:
    """Evaluate supplied candidate strategies for an owned scan target."""

    def __init__(
        self,
        context_builder: ContextBuilder,
        provider: StrategyEvaluationProvider,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._context_builder = context_builder
        self._provider = provider
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def evaluate_strategies(
        self,
        user_id: str,
        scan_id: str,
        *,
        issue_id: Optional[str] = None,
        group_id: Optional[str] = None,
        strategies: List[CandidateStrategy],
    ) -> EvaluationBatch:
        """Evaluate every supplied strategy against the scan's context.

        :raises ScanNotFoundError: missing or foreign scan (404-safe).
        :raises ContextUnavailableError: the scan has not completed (409).
        :raises EvaluationTargetNotFoundError: unknown issue/group (404).
        :raises EvaluationStrategyInvalidError: a strategy does not match the
            target/context (422).
        :raises EvaluationConfigurationError / EvaluationProviderError /
            EvaluationOutputError: provider problems (503/502).
        """
        context = await self._context_builder.build_for_scan(user_id, scan_id)
        target = self._resolve_target(context, issue_id=issue_id, group_id=group_id)
        self._validate_strategies(context, target, strategies)

        evaluations: List[StrategyEvaluation] = []
        system_prompt = build_evaluation_system_prompt()
        for strategy in strategies:
            user_prompt = build_evaluation_user_prompt(context, strategy, target)
            request = StrategyEvaluationRequest(
                prompt_version=EVALUATION_PROMPT_VERSION,
                evaluation_version=EVALUATION_VERSION,
                context_version=context.context_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                strategy=strategy,
                target=target,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            draft = await self._provider.evaluate(request)
            if draft.strategy_id != strategy.strategy_id:
                raise EvaluationOutputError(
                    "The evaluator returned an evaluation for a different "
                    "strategy than the one supplied."
                )
            evaluations.append(
                self._stamp(draft, context, target, scan_id)
            )

        return EvaluationBatch(
            scan_id=scan_id,
            issue_id=target.issue_id,
            group_id=target.group_id,
            context_version=context.context_version,
            evaluation_version=EVALUATION_VERSION,
            prompt_version=EVALUATION_PROMPT_VERSION,
            provider=self._provider.name,
            model=self._model,
            evaluations=evaluations,
        )

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
                raise EvaluationTargetNotFoundError(
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

        raise EvaluationTargetNotFoundError(
            "Provide an issue_id or group_id to evaluate strategies for."
        )

    # --- strategy validation --------------------------------------------------

    @staticmethod
    def _validate_strategies(
        context: ContextDocument,
        target: StrategyTarget,
        strategies: List[CandidateStrategy],
    ) -> None:
        """Re-validate every supplied strategy against the deterministic
        context so client-supplied ids can never be trusted blindly."""
        primary_issue_id = target.issue_id or (
            target.issues[0].issue_id if target.issues else ""
        )
        reference = target.issue_id or target.group_id or primary_issue_id

        for strategy in strategies:
            if strategy.issue_id != primary_issue_id:
                raise EvaluationStrategyInvalidError(
                    "A supplied strategy does not belong to the selected target."
                )
            if strategy.context_version != context.context_version:
                raise EvaluationStrategyInvalidError(
                    "A supplied strategy was generated for a different context "
                    "version."
                )
            if strategy.evidence_reference != reference:
                raise EvaluationStrategyInvalidError(
                    "A supplied strategy does not reference the selected target."
                )
            if target.group_id:
                if strategy.group_id != target.group_id:
                    raise EvaluationStrategyInvalidError(
                        "A supplied strategy does not belong to the selected group."
                    )
            elif strategy.group_id is not None:
                raise EvaluationStrategyInvalidError(
                    "A group strategy was supplied for an issue target."
                )

    # --- stamping -------------------------------------------------------------

    def _stamp(
        self,
        draft: EvaluationDraft,
        context: ContextDocument,
        target: StrategyTarget,
        scan_id: str,
    ) -> StrategyEvaluation:
        primary_issue_id = target.issue_id or (
            target.issues[0].issue_id if target.issues else ""
        )
        return StrategyEvaluation(
            evaluation_id=f"eval-{draft.strategy_id}",
            strategy_id=draft.strategy_id,
            scan_id=scan_id,
            issue_id=primary_issue_id,
            group_id=target.group_id,
            context_version=context.context_version,
            evaluation_version=EVALUATION_VERSION,
            **draft.model_dump(exclude={"strategy_id"}),
            evaluator_provider=self._provider.name,
            evaluator_model=self._model,
            prompt_version=EVALUATION_PROMPT_VERSION,
            evaluated_at=datetime.now(timezone.utc),
        )


def _find_issue(context: ContextDocument, issue_id: str) -> IssueContext:
    for issue in context.issues:
        if issue.issue_id == issue_id:
            return issue
    raise EvaluationTargetNotFoundError("The issue was not found for this scan.")


def _find_group(context: ContextDocument, group_id: str) -> IssueGroup:
    for group in context.groups:
        if group.group_id == group_id:
            return group
    raise EvaluationTargetNotFoundError("The group was not found for this scan.")
