"""Tests for the strategy generation service (Module 4).

The service is exercised against in-memory repository fakes + the real
ContextBuilderService (so real deterministic grouping is used) and the mock
provider (deterministic). Provider failure modes (too few, too many,
duplicates) use a configurable fake provider.

Covers: issue/group targets, both-supplied consistency, missing/foreign scan
(404-safe), non-completed scan (409), metadata traceability, count and
uniqueness validation, and secret-free responses.
"""

import asyncio
from typing import List, Optional

import pytest

from app.context.exceptions import ContextUnavailableError
from app.context.services import ContextBuilderService
from app.core.config import Settings
from app.scans.exceptions import ScanNotFoundError
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.strategies.exceptions import (
    StrategyOutputError,
    StrategyTargetNotFoundError,
)
from app.strategies.models import (
    CandidateStrategy,
    StrategyGenerationRequest,
)
from app.strategies.providers.mock import MockStrategyProvider
from app.strategies.services import StrategyGenerationService
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


class FakeProvider:
    """Configurable provider: fixed list or a raising callable."""

    name = "fake"

    def __init__(
        self, strategies: Optional[List[CandidateStrategy]] = None, error=None
    ) -> None:
        self._strategies = strategies
        self._error = error

    async def generate(self, request: StrategyGenerationRequest) -> List[CandidateStrategy]:
        if self._error is not None:
            raise self._error
        if self._strategies is None:
            return [
                CandidateStrategy.model_validate(make_strategy(strategy_id=f"s{i}", strategy_index=i))
                for i in range(1, 4)
            ]
        return self._strategies


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def harness() -> tuple[StrategyGenerationService, FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    scans, issues, projects = FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    settings = Settings(llm_provider="mock", llm_model="mock-model")
    provider = MockStrategyProvider(settings)
    service = StrategyGenerationService(
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
    """Seed an owned scan with issues; returns the scan id."""
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(
        issues.insert_many(
            scan.id, [make_issue(rule_id=r) for r in (rule_ids or ["color-contrast"])]
        )
    )
    return scan.id


def test_generate_for_issue_target(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    result = run(service.generate_strategies("user-a", scan_id, issue_id=issues.issues_for(scan_id)[0].id))

    assert result.metadata.scan_id == scan_id
    assert result.metadata.target_type == "issue"
    assert result.metadata.provider == "mock"
    assert result.metadata.model == "mock-model"
    assert result.metadata.context_version == "1.0"
    assert result.metadata.prompt_version == "1.0"
    assert result.metadata.strategy_count == 3
    assert len(result.strategies) == 3
    for strategy in result.strategies:
        assert strategy.issue_id == issues.issues_for(scan_id)[0].id
        assert strategy.context_version == "1.0"
        assert strategy.evidence_reference == issues.issues_for(scan_id)[0].id
        assert 1 <= strategy.strategy_index <= 3
        assert result.metadata.group_id is None


def test_generate_for_group_target(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, rule_ids=["color-contrast", "color-contrast"])

    context = run(service._context_builder.build_for_scan("user-a", scan_id))
    group = next(g for g in context.groups if g.group_type == "same_rule")

    result = run(service.generate_strategies("user-a", scan_id, group_id=group.group_id))

    assert result.metadata.target_type == "group"
    assert result.metadata.group_id == group.group_id
    assert len(result.strategies) == 3
    assert all(s.group_id == group.group_id for s in result.strategies)
    assert all(s.evidence_reference == group.group_id for s in result.strategies)


def test_generate_with_issue_and_matching_group(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, rule_ids=["color-contrast"])
    issue_id = issues.issues_for(scan_id)[0].id
    context = run(service._context_builder.build_for_scan("user-a", scan_id))
    group = next(g for g in context.groups if g.group_type == "same_rule")

    result = run(
        service.generate_strategies("user-a", scan_id, issue_id=issue_id, group_id=group.group_id)
    )

    assert result.metadata.target_type == "group"
    assert result.metadata.issue_id == issue_id


def test_generate_with_issue_not_in_group_rejected(harness) -> None:
    service, scans, issues, projects = harness
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id, status=ScanStatus.COMPLETED)
    run(
        issues.insert_many(
            scan.id,
            [
                make_issue(rule_id="color-contrast"),
                make_issue(rule_id="image-alt", tags=["wcag2a", "wcag111"]),
            ],
        )
    )
    scan_id = scan.id
    issue_id = issues.issues_for(scan_id)[0].id  # the color-contrast issue
    context = run(service._context_builder.build_for_scan("user-a", scan_id))
    # a wcag group that belongs to the other issue (wcag:1.1.1)
    other_group = next(
        g for g in context.groups if g.group_type == "wcag" and issue_id not in g.issue_ids
    )

    with pytest.raises(StrategyTargetNotFoundError):
        run(
            service.generate_strategies(
                "user-a", scan_id, issue_id=issue_id, group_id=other_group.group_id
            )
        )


def test_generate_missing_issue_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(StrategyTargetNotFoundError):
        run(service.generate_strategies("user-a", scan_id, issue_id="no-such-issue"))


def test_generate_missing_group_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(StrategyTargetNotFoundError):
        run(service.generate_strategies("user-a", scan_id, group_id="rule:no-such"))


def test_generate_without_target_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)

    with pytest.raises(StrategyTargetNotFoundError):
        run(service.generate_strategies("user-a", scan_id))


def test_generate_foreign_scan_404(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, user_id="user-b")

    with pytest.raises(ScanNotFoundError):
        run(service.generate_strategies("user-a", scan_id, issue_id="x"))


def test_generate_missing_scan_404(harness) -> None:
    service, scans, issues, projects = harness

    with pytest.raises(ScanNotFoundError):
        run(service.generate_strategies("user-a", "no-such-scan", issue_id="x"))


def test_generate_running_scan_409(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects, status=ScanStatus.RUNNING)

    with pytest.raises(ContextUnavailableError):
        run(service.generate_strategies("user-a", scan_id, issue_id="x"))


def test_provider_returning_too_few_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(
        strategies=[CandidateStrategy.model_validate(make_strategy(strategy_id="only"))]
    )

    with pytest.raises(StrategyOutputError):
        run(service.generate_strategies("user-a", scan_id, issue_id=issue_id))


def test_provider_returning_too_many_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(
        strategies=[
            CandidateStrategy.model_validate(
                make_strategy(strategy_id=f"s{i}", strategy_index=(i % 5) + 1)
            )
            for i in range(1, 7)
        ]
    )

    with pytest.raises(StrategyOutputError):
        run(service.generate_strategies("user-a", scan_id, issue_id=issue_id))


def test_provider_duplicate_ids_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(
        strategies=[
            CandidateStrategy.model_validate(make_strategy(strategy_id="dup", strategy_index=i))
            for i in (1, 2)
        ]
    )

    with pytest.raises(StrategyOutputError):
        run(service.generate_strategies("user-a", scan_id, issue_id=issue_id))


def test_provider_duplicate_titles_rejected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(
        strategies=[
            CandidateStrategy.model_validate(
                make_strategy(strategy_id=f"s{i}", strategy_index=i, title="Same Title")
            )
            for i in (1, 2)
        ]
    )

    with pytest.raises(StrategyOutputError):
        run(service.generate_strategies("user-a", scan_id, issue_id=issue_id))


def test_provider_failure_propagates(harness) -> None:
    from app.strategies.exceptions import StrategyProviderError

    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id
    service._provider = FakeProvider(error=StrategyProviderError("The provider is down."))

    with pytest.raises(StrategyProviderError):
        run(service.generate_strategies("user-a", scan_id, issue_id=issue_id))


def test_strategy_count_respected(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    result = run(service.generate_strategies("user-a", scan_id, issue_id=issue_id, strategy_count=5))

    assert result.metadata.strategy_count == 5
    assert len(result.strategies) == 5
    assert [s.strategy_index for s in result.strategies] == [1, 2, 3, 4, 5]


def test_generation_response_has_no_secrets(harness) -> None:
    service, scans, issues, projects = harness
    scan_id = seed_scan(scans, issues, projects)
    issue_id = issues.issues_for(scan_id)[0].id

    body = run(
        service.generate_strategies("user-a", scan_id, issue_id=issue_id)
    ).model_dump()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized
