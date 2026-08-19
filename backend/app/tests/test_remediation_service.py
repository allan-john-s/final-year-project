"""Tests for the remediation service (Module 7).

Covers proposal generation, ownership validation, strategy verification,
status transitions, and error handling. Uses fake repos and the mock
provider — no LLM, no network, no Supabase.
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock

import pytest

from app.context.services import ContextBuilderService
from app.evaluations.models import StrategyEvaluation
from app.remediations.exceptions import (
    RemediationInvalidTransitionError,
    RemediationStrategyNotRankedError,
    RemediationTargetNotFoundError,
)
from app.remediations.models import RemediationProposal, RemediationStatus
from app.remediations.providers.mock import MockRemediationProvider
from app.remediations.services import RemediationService
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.strategies.models import CandidateStrategy
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)
from app.tests.test_strategy_models import make_strategy


def run(coro):
    return asyncio.run(coro)


# --- helpers ---------------------------------------------------------------


def make_issue(rule_id="color-contrast", **overrides) -> AccessibilityIssue:
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


def make_strat(issue_id: str, strategy_id: str = "s-1", **overrides) -> CandidateStrategy:
    data = make_strategy(strategy_id=strategy_id, issue_id=issue_id, evidence_reference=issue_id)
    data.update(overrides)
    return CandidateStrategy.model_validate(data)


def make_eval(
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
        evaluation_version="1.0",
        **scores,
        strengths=["A strength."],
        weaknesses=["A weakness."],
        rationale="A rationale referencing the evidence.",
        assumptions=[],
        uncertainties=[],
        evidence_references=[issue_id],
        evaluator_provider="mock",
        evaluator_model="mock-model",
        prompt_version="1.0",
    )


@pytest.fixture
def repos():
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


@pytest.fixture
def service_with_scan(repos):
    """Set up a completed scan with one issue and return (service, scan_id, issue_id)."""
    scans, issues, projects = repos
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    provider = MockRemediationProvider()
    svc = RemediationService(context_builder=context_builder, provider=provider)

    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run(issues.insert_many(scan.id, [make_issue()]))
    issue_id = issues.issues_for(scan.id)[0].id
    return svc, scan.id, issue_id


# --- proposal generation ---------------------------------------------------


def test_generate_proposal_returns_structured_proposal(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, f"s-{i}") for i in (1, 2, 3)]
    evaluations = [make_eval(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2, 3)]

    proposal = run(svc.generate_proposal(
        "user-a", scan_id,
        issue_id=issue_id,
        strategy_id="s-1",
        strategies=strategies,
        evaluations=evaluations,
    ))

    assert isinstance(proposal, RemediationProposal)
    assert proposal.scan_id == scan_id
    assert proposal.issue_id == issue_id
    assert proposal.strategy_id == "s-1"
    assert proposal.status is RemediationStatus.PROPOSED
    assert proposal.provider == "mock"
    assert proposal.title
    assert proposal.summary
    assert proposal.rationale
    assert proposal.implementation_steps
    assert proposal.proposed_change.before
    assert proposal.proposed_change.after
    assert proposal.proposed_change.explanation
    assert proposal.validation_steps
    assert 0 <= proposal.confidence <= 1


def test_generate_proposal_default_is_rank_1(service_with_scan):
    """When all strategies have identical scores, s-1 wins by tie-break (alphabetical)."""
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, f"s-{i}") for i in (1, 2)]
    evaluations = [make_eval(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    proposal = run(svc.generate_proposal(
        "user-a", scan_id,
        issue_id=issue_id,
        strategy_id="s-1",
        strategies=strategies,
        evaluations=evaluations,
    ))

    assert proposal.rank == 1


def test_generate_proposal_rejects_non_top_ranked(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, f"s-{i}") for i in (1, 2)]
    evaluations = [
        make_eval("s-1", scan_id=scan_id, issue_id=issue_id, accessibility_impact_score=10),
        make_eval("s-2", scan_id=scan_id, issue_id=issue_id, accessibility_impact_score=2),
    ]

    with pytest.raises(RemediationStrategyNotRankedError) as exc_info:
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-2",  # lower-ranked strategy
            strategies=strategies,
            evaluations=evaluations,
        ))
    assert "ranked" in str(exc_info.value).lower()


# --- error cases -----------------------------------------------------------


def test_generate_proposal_foreign_scan(repos):
    scans, issues, projects = repos
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    svc = RemediationService(context_builder=context_builder, provider=MockRemediationProvider())

    project = projects.seed("user-b")
    scan = scans.seed("user-b", project_id=project.id)
    run(issues.insert_many(scan.id, [make_issue()]))

    strategies = [make_strat("issue-x")]
    evaluations = [make_eval("s-1")]

    with pytest.raises(Exception):  # scan not found
        run(svc.generate_proposal(
            "user-a", scan.id,
            issue_id="issue-x",
            strategy_id="s-1",
            strategies=strategies,
            evaluations=evaluations,
        ))


def test_generate_proposal_unknown_issue(service_with_scan):
    svc, scan_id, _issue_id = service_with_scan
    strategies = [make_strat("nonexistent")]
    evaluations = [make_eval("s-1")]

    with pytest.raises(RemediationTargetNotFoundError):
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id="nonexistent",
            strategy_id="s-1",
            strategies=strategies,
            evaluations=evaluations,
        ))


def test_generate_proposal_strategy_not_in_list(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, "s-1")]
    evaluations = [make_eval("s-1", scan_id=scan_id, issue_id=issue_id)]

    with pytest.raises(RemediationTargetNotFoundError):
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-missing",
            strategies=strategies,
            evaluations=evaluations,
        ))


def test_generate_proposal_strategy_wrong_issue(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    # Strategy belongs to a different issue
    strategies = [make_strat("other-issue", "s-1")]
    evaluations = [make_eval("s-1", scan_id=scan_id, issue_id="other-issue")]

    with pytest.raises(RemediationTargetNotFoundError):
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-1",
            strategies=strategies,
            evaluations=evaluations,
        ))


def test_generate_proposal_no_evaluation(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, "s-1")]
    # No evaluations provided

    with pytest.raises(RemediationTargetNotFoundError):
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-1",
            strategies=strategies,
            evaluations=[],
        ))


# --- provider failure ------------------------------------------------------


def test_provider_failure_wrapped(service_with_scan):
    svc, scan_id, issue_id = service_with_scan

    class FailProvider:
        name = "fail"
        async def generate_proposal(self, **kwargs):
            raise RuntimeError("Provider crashed")

    svc._provider = FailProvider()
    strategies = [make_strat(issue_id, "s-1")]
    evaluations = [make_eval("s-1", scan_id=scan_id, issue_id=issue_id)]

    from app.remediations.exceptions import RemediationProviderError
    with pytest.raises(RemediationProviderError):
        run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-1",
            strategies=strategies,
            evaluations=evaluations,
        ))


# --- status transitions ---------------------------------------------------


def test_valid_status_transitions():
    from app.remediations.models import is_valid_transition

    assert is_valid_transition(RemediationStatus.PROPOSED, RemediationStatus.REVIEWED)
    assert is_valid_transition(RemediationStatus.REVIEWED, RemediationStatus.ACCEPTED)
    assert is_valid_transition(RemediationStatus.REVIEWED, RemediationStatus.REJECTED)
    assert is_valid_transition(RemediationStatus.ACCEPTED, RemediationStatus.APPLIED)


def test_invalid_status_transition_raises():
    with pytest.raises(RemediationInvalidTransitionError):
        RemediationService.validate_status_transition(
            RemediationStatus.PROPOSED, RemediationStatus.ACCEPTED
        )
    with pytest.raises(RemediationInvalidTransitionError):
        RemediationService.validate_status_transition(
            RemediationStatus.REJECTED, RemediationStatus.PROPOSED
        )


def test_complete_status_lifecycle():
    """Walk through the full lifecycle: PROPOSED -> REVIEWED -> ACCEPTED -> APPLIED."""
    from app.remediations.models import is_valid_transition

    steps = [
        RemediationStatus.PROPOSED,
        RemediationStatus.REVIEWED,
        RemediationStatus.ACCEPTED,
        RemediationStatus.APPLIED,
    ]
    for current, target in zip(steps, steps[1:]):
        assert is_valid_transition(current, target)


def test_reviewed_to_rejected():
    from app.remediations.models import is_valid_transition
    assert is_valid_transition(RemediationStatus.REVIEWED, RemediationStatus.REJECTED)


# --- deterministic output --------------------------------------------------


def test_mock_provider_is_deterministic(service_with_scan):
    svc, scan_id, issue_id = service_with_scan
    strategies = [make_strat(issue_id, "s-1")]
    evaluations = [make_eval("s-1", scan_id=scan_id, issue_id=issue_id)]

    proposals = []
    for _ in range(3):
        p = run(svc.generate_proposal(
            "user-a", scan_id,
            issue_id=issue_id,
            strategy_id="s-1",
            strategies=strategies,
            evaluations=evaluations,
        ))
        proposals.append(p)

    # Title, summary, rationale should be identical (except id has uuid)
    assert proposals[0].title == proposals[1].title == proposals[2].title
    assert proposals[0].summary == proposals[1].summary == proposals[2].summary
    assert proposals[0].rationale == proposals[1].rationale == proposals[2].rationale
