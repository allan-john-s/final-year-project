"""Tests for the strategy ranking service (Module 6).

The service is exercised against in-memory repository fakes + the real
ContextBuilderService (deterministic grouping). Covers: target resolution,
ownership (404-safe), non-completed scans (409), baseline vs contextual
ranking, comparison, determinism, and the no-secrets guarantee.
"""

import asyncio

import pytest

from app.context.exceptions import ContextUnavailableError
from app.context.services import ContextBuilderService
from app.evaluations.models import StrategyEvaluation
from app.rankings.exceptions import (
    RankingEvaluationsNotFoundError,
    RankingTargetNotFoundError,
)
from app.rankings.models import RankingMode
from app.rankings.services import StrategyRankingService
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
    data = make_strategy(
        strategy_id=strategy_id,
        issue_id=issue_id,
        evidence_reference=issue_id,
    )
    data.update(overrides)
    return CandidateStrategy.model_validate(data)


def make_evaluation(
    strategy_id: str,
    scan_id: str = "scan-1",
    issue_id: str = "issue-1",
    **score_overrides,
) -> StrategyEvaluation:
    scores = {
        "accessibility_impact_score": 7,
        "standards_compliance_score": 8,
        "contextual_suitability_score": 7,
        "implementation_effort_score": 6,
        "maintainability_score": 7,
        "compatibility_score": 8,
        "risk_score": 7,
    }
    scores.update(score_overrides)
    return StrategyEvaluation(
        evaluation_id=f"eval-{strategy_id}",
        strategy_id=strategy_id,
        scan_id=scan_id,
        issue_id=issue_id,
        context_version="1.0",
        evaluator_provider="mock",
        evaluator_model="mock-model",
        prompt_version="1.0",
        strengths=["A strength."],
        weaknesses=["A weakness."],
        rationale="A rationale.",
        **scores,
    )


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def harness():
    scans, issues, projects = FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    service = StrategyRankingService(context_builder=context_builder)
    return service, scans, issues, projects


def seed_scan(
    scans, issues, projects,
    *, user_id="user-a", status=ScanStatus.COMPLETED, rule_ids=None,
):
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(
        issues.insert_many(
            scan.id, [make_issue(rule_id=r) for r in (rule_ids or ["color-contrast"])]
        )
    )
    return scan.id


def test_rank_strategies_for_issue(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)]
    evaluations = [make_evaluation(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2, 3)]

    batch = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.BASELINE,
        )
    )

    assert batch.scan_id == scan_id
    assert batch.issue_id == issue_id
    assert batch.group_id is None
    assert batch.ranking_method == "baseline"
    assert batch.context_version == "1.0"
    assert batch.ranking_version == "1.0"
    assert len(batch.ranked_strategies) == 3
    assert batch.ranked_strategies[0].rank == 1
    assert batch.ranked_strategies[0].strategy_id == "s-1"  # tie-break by id ascending
    assert batch.weights_used.total() == pytest.approx(1.0, abs=0.01)


def test_rank_strategies_contextual(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [make_evaluation(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    batch = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.CONTEXTUAL,
        )
    )

    assert batch.ranking_method == "contextual"
    assert len(batch.context_factors) >= 5
    assert len(batch.ranked_strategies) == 2


def test_rank_for_group(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, rule_ids=["color-contrast", "color-contrast"])
    context = run(service._context_builder.build_for_scan("user-a", scan_id))
    group = next(g for g in context.groups if g.group_type == "same_rule")
    primary_issue_id = context.issues[0].issue_id
    strategies = [
        make_candidate(primary_issue_id, strategy_id=f"s-{i}", group_id=group.group_id, evidence_reference=group.group_id)
        for i in (1, 2)
    ]
    evaluations = [
        make_evaluation(f"s-{i}", scan_id=scan_id, issue_id=primary_issue_id)
        for i in (1, 2)
    ]

    batch = run(
        service.rank_strategies(
            "user-a", scan_id, group_id=group.group_id, strategies=strategies,
            evaluations=evaluations,
        )
    )

    assert batch.group_id == group.group_id
    assert len(batch.ranked_strategies) == 2


def test_foreign_scan_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, user_id="user-b")
    strategies = [make_candidate("x", strategy_id="s-1")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(ScanNotFoundError):
        run(
            service.rank_strategies(
                "user-a", scan_id, issue_id="x", strategies=strategies,
                evaluations=evaluations,
            )
        )


def test_missing_scan_404(harness) -> None:
    service, scans, issues, projects = harness
    strategies = [make_candidate("x", strategy_id="s-1")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(ScanNotFoundError):
        run(
            service.rank_strategies(
                "user-a", "no-such-scan", issue_id="x", strategies=strategies,
                evaluations=evaluations,
            )
        )


def test_running_scan_409(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, status=ScanStatus.RUNNING)
    strategies = [make_candidate("x", strategy_id="s-1")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(ContextUnavailableError):
        run(
            service.rank_strategies(
                "user-a", scan_id, issue_id="x", strategies=strategies,
                evaluations=evaluations,
            )
        )


def test_unknown_issue_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    strategies = [make_candidate("no-such", strategy_id="s-1")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(RankingTargetNotFoundError):
        run(
            service.rank_strategies(
                "user-a", scan_id, issue_id="no-such", strategies=strategies,
                evaluations=evaluations,
            )
        )


def test_unknown_group_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    strategies = [make_candidate("x", strategy_id="s-1", group_id="rule:no-such", evidence_reference="rule:no-such")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(RankingTargetNotFoundError):
        run(
            service.rank_strategies(
                "user-a", scan_id, group_id="rule:no-such", strategies=strategies,
                evaluations=evaluations,
            )
        )


def test_no_target_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    strategies = [make_candidate("x", strategy_id="s-1")]
    evaluations = [make_evaluation("s-1")]

    with pytest.raises(RankingTargetNotFoundError):
        run(
            service.rank_strategies(
                "user-a", scan_id, strategies=strategies, evaluations=evaluations,
            )
        )


def test_no_evaluations_409(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id="s-1")]

    with pytest.raises(RankingEvaluationsNotFoundError):
        run(
            service.rank_strategies(
                "user-a", scan_id, issue_id=issue_id, strategies=strategies,
                evaluations=[],
            )
        )


def test_ranking_is_deterministic(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)]
    evaluations = [make_evaluation(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2, 3)]

    first = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.BASELINE,
        )
    )
    second = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.BASELINE,
        )
    )

    def content(batch):
        return [
            r.model_dump(exclude={"generated_at"})
            for r in batch.ranked_strategies
        ]

    assert content(first) == content(second)


def test_response_has_no_secrets(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id="s-1")]
    evaluations = [make_evaluation("s-1", scan_id=scan_id, issue_id=issue_id)]

    batch = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations,
        )
    )

    serialized = str(batch.model_dump()).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_baseline_vs_contextual_both_produce_rankings(harness) -> None:
    """Both modes produce valid rankings with the same strategies."""
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    strategies = [make_candidate(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)]
    evaluations = [make_evaluation(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2, 3)]

    baseline = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.BASELINE,
        )
    )
    contextual = run(
        service.rank_strategies(
            "user-a", scan_id, issue_id=issue_id, strategies=strategies,
            evaluations=evaluations, mode=RankingMode.CONTEXTUAL,
        )
    )

    assert baseline.ranking_method == "baseline"
    assert contextual.ranking_method == "contextual"
    assert len(baseline.ranked_strategies) == 3
    assert len(contextual.ranked_strategies) == 3
    # Both rank the same strategies
    assert set(r.strategy_id for r in baseline.ranked_strategies) == set(
        r.strategy_id for r in contextual.ranked_strategies
    )
