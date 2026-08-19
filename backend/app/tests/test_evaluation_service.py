"""Tests for the strategy evaluation service (Module 5).

The service is exercised against in-memory repository fakes + the real
ContextBuilderService (deterministic grouping) and the mock evaluator
(deterministic). Covers: per-strategy independent evaluations, batch
metadata, issue/group targets, ownership (404-safe), non-completed scans
(409), strategy/context mismatch rejection (422), provider failures,
determinism, and the no-total/no-rank/no-secrets guarantees.
"""

import asyncio
from typing import List, Optional

import pytest

from app.context.exceptions import ContextUnavailableError
from app.context.services import ContextBuilderService
from app.core.config import Settings
from app.evaluations.exceptions import (
    EvaluationOutputError,
    EvaluationProviderError,
    EvaluationStrategyInvalidError,
    EvaluationTargetNotFoundError,
)
from app.evaluations.models import EvaluationDraft, StrategyEvaluationRequest
from app.evaluations.providers.mock import MockEvaluationProvider
from app.evaluations.services import StrategyEvaluationService
from app.scans.exceptions import ScanNotFoundError
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.strategies.models import CandidateStrategy
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)
from app.tests.test_strategy_models import make_strategy


def make_issue(rule_id: str = "color-contrast", **overrides) -> AccessibilityIssue:
    defaults = {
        "rule_id": rule_id,
        "rule_name": "Elements must have sufficient color contrast",
        "impact": Impact.SERIOUS,
        "wcag_level": WcagLevel.AA,
        "tags": ["wcag2aa", "wcag143"],
        "element_selector": "#main > p",
        "html_snippet": '<p class="muted">Low contrast text</p>',
        "failure_summary": "Element has insufficient color contrast.",
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


def make_candidate(issue_id: str, strategy_id: str = "native-1", **overrides) -> CandidateStrategy:
    """A valid candidate strategy dict matching the target context."""
    data = make_strategy(
        strategy_id=strategy_id,
        issue_id=issue_id,
        evidence_reference=issue_id,
    )
    data.update(overrides)
    return CandidateStrategy.model_validate(data)


class FakeProvider:
    """Configurable provider: a fixed draft or a raising callable."""

    name = "fake"

    def __init__(self, draft=None, error=None, wrong_strategy_id: bool = False) -> None:
        self._draft = draft
        self._error = error
        self._wrong_strategy_id = wrong_strategy_id

    async def evaluate(self, request: StrategyEvaluationRequest) -> EvaluationDraft:
        if self._error is not None:
            raise self._error
        if self._draft is not None:
            return self._draft
        strategy = request.strategy
        if self._wrong_strategy_id:
            strategy_id = "someone-else"
        else:
            strategy_id = strategy.strategy_id
        return EvaluationDraft(
            strategy_id=strategy_id,
            accessibility_impact_score=7,
            standards_compliance_score=8,
            contextual_suitability_score=7,
            implementation_effort_score=6,
            maintainability_score=7,
            compatibility_score=8,
            risk_score=7,
            strengths=["A strength."],
            weaknesses=["A weakness."],
            rationale="A rationale referencing the supplied evidence.",
            assumptions=["An assumption."],
            uncertainties=["An uncertainty."],
            evidence_references=[strategy.evidence_reference or strategy.issue_id],
        )


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def harness() -> tuple[StrategyEvaluationService, FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    scans, issues, projects = FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    settings = Settings(llm_provider="mock", llm_model="mock-model")
    provider = MockEvaluationProvider(settings)
    service = StrategyEvaluationService(
        context_builder=context_builder,
        provider=provider,
        model="mock-model",
        temperature=0.2,
        max_tokens=1000,
    )
    return service, scans, issues, projects


def seed_scan(
    scans: FakeScanRepository,
    issues: FakeIssueRepository,
    projects: FakeProjectRepository,
    *,
    user_id: str = "user-a",
    status: ScanStatus = ScanStatus.COMPLETED,
    rule_ids: Optional[List[str]] = None,
) -> str:
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(
        issues.insert_many(
            scan.id, [make_issue(rule_id=r) for r in (rule_ids or ["color-contrast"])]
        )
    )
    return scan.id


def test_evaluate_three_strategies_independently(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [
        make_candidate(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)
    ]

    batch = run(
        service.evaluate_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies
        )
    )

    assert batch.scan_id == scan_id
    assert batch.issue_id == issue_id
    assert batch.group_id is None
    assert batch.context_version == "1.0"
    assert batch.evaluation_version == "1.0"
    assert batch.prompt_version == "1.0"
    assert batch.provider == "mock"
    assert batch.model == "mock-model"
    assert len(batch.evaluations) == 3
    for evaluation, strategy in zip(batch.evaluations, strategies):
        assert evaluation.strategy_id == strategy.strategy_id
        assert evaluation.evaluation_id == f"eval-{strategy.strategy_id}"
        assert evaluation.scan_id == scan_id
        assert evaluation.issue_id == issue_id
        assert evaluation.context_version == "1.0"
        assert evaluation.evaluator_provider == "mock"
        assert evaluation.evaluator_model == "mock-model"
        assert evaluation.evaluated_at is not None
        for field in (
            "accessibility_impact_score",
            "standards_compliance_score",
            "contextual_suitability_score",
            "implementation_effort_score",
            "maintainability_score",
            "compatibility_score",
            "risk_score",
        ):
            assert 0 <= getattr(evaluation, field) <= 10
        assert evaluation.strengths
        assert evaluation.weaknesses
        assert evaluation.rationale


def test_evaluate_for_group_target(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, rule_ids=["color-contrast", "color-contrast"])
    context = run(service._context_builder.build_for_scan("user-a", scan_id))
    group = next(g for g in context.groups if g.group_type == "same_rule")
    primary_issue_id = context.issues[0].issue_id  # deterministic first member

    strategies = [
        make_candidate(
            primary_issue_id,
            strategy_id=f"s-{i}",
            group_id=group.group_id,
            evidence_reference=group.group_id,
        )
        for i in (1, 2)
    ]

    batch = run(
        service.evaluate_strategies(
            "user-a", scan_id, group_id=group.group_id, strategies=strategies
        )
    )

    assert batch.group_id == group.group_id
    assert batch.issue_id is None
    assert len(batch.evaluations) == 2
    assert all(e.group_id == group.group_id for e in batch.evaluations)


def test_evaluation_is_deterministic(harness) -> None:
    """Identical inputs produce identical evaluation content (timestamps are
    metadata and excluded from the comparison)."""
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id="s-1")]

    first = run(
        service.evaluate_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies
        )
    )
    second = run(
        service.evaluate_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies
        )
    )

    def content(batch) -> list:
        return [
            e.model_dump(exclude={"evaluated_at"}) for e in batch.evaluations
        ]

    assert content(first) == content(second)


def test_foreign_scan_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, user_id="user-b")

    with pytest.raises(ScanNotFoundError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, issue_id="x", strategies=[make_candidate("x")]
            )
        )


def test_missing_scan_404(harness) -> None:
    service, scans, issues, projects = harness

    with pytest.raises(ScanNotFoundError):
        run(
            service.evaluate_strategies(
                "user-a", "no-such-scan", issue_id="x", strategies=[make_candidate("x")]
            )
        )


def test_running_scan_409(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, status=ScanStatus.RUNNING)

    with pytest.raises(ContextUnavailableError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, issue_id="x", strategies=[make_candidate("x")]
            )
        )


def test_missing_issue_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(EvaluationTargetNotFoundError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, issue_id="no-such-issue", strategies=[make_candidate("no-such-issue")]
            )
        )


def test_missing_group_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(EvaluationTargetNotFoundError):
        run(
            service.evaluate_strategies(
                "user-a",
                scan_id,
                group_id="rule:no-such",
                strategies=[make_candidate("x", group_id="rule:no-such", evidence_reference="rule:no-such")],
            )
        )


def test_evaluate_without_target_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(EvaluationTargetNotFoundError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, strategies=[make_candidate("x")]
            )
        )


def test_strategy_with_wrong_issue_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    with pytest.raises(EvaluationStrategyInvalidError):
        run(
            service.evaluate_strategies(
                "user-a",
                scan_id,
                issue_id=issue_id,
                strategies=[make_candidate("other-issue", strategy_id="s-1")],
            )
        )


def test_strategy_with_wrong_context_version_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    with pytest.raises(EvaluationStrategyInvalidError):
        run(
            service.evaluate_strategies(
                "user-a",
                scan_id,
                issue_id=issue_id,
                strategies=[make_candidate(issue_id, strategy_id="s-1", context_version="9.9")],
            )
        )


def test_strategy_with_wrong_evidence_reference_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    with pytest.raises(EvaluationStrategyInvalidError):
        run(
            service.evaluate_strategies(
                "user-a",
                scan_id,
                issue_id=issue_id,
                strategies=[make_candidate(issue_id, strategy_id="s-1", evidence_reference="other")],
            )
        )


def test_group_strategy_for_issue_target_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    with pytest.raises(EvaluationStrategyInvalidError):
        run(
            service.evaluate_strategies(
                "user-a",
                scan_id,
                issue_id=issue_id,
                strategies=[
                    make_candidate(
                        issue_id, strategy_id="s-1", group_id="rule:x", evidence_reference="rule:x"
                    )
                ],
            )
        )


def test_provider_failure_propagates(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(error=EvaluationProviderError("The evaluator is down."))

    with pytest.raises(EvaluationProviderError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, issue_id=issue_id, strategies=[make_candidate(issue_id)]
            )
        )


def test_provider_evaluating_wrong_strategy_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(wrong_strategy_id=True)

    with pytest.raises(EvaluationOutputError):
        run(
            service.evaluate_strategies(
                "user-a", scan_id, issue_id=issue_id, strategies=[make_candidate(issue_id)]
            )
        )


def test_response_has_no_secrets(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    body = run(
        service.evaluate_strategies(
            "user-a",
            scan_id,
            issue_id=issue_id,
            strategies=[make_candidate(issue_id, strategy_id="s-1")],
        )
    ).model_dump()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_response_has_no_total_score_and_no_rank(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    body = run(
        service.evaluate_strategies(
            "user-a",
            scan_id,
            issue_id=issue_id,
            strategies=[make_candidate(issue_id, strategy_id="s-1")],
        )
    ).model_dump()

    serialized = str(body).lower()
    assert "total_score" not in serialized
    assert '"rank"' not in serialized
    assert "winner" not in serialized
    for forbidden in ("best strategy", "recommended strategy", "optimal strategy"):
        assert forbidden not in serialized
