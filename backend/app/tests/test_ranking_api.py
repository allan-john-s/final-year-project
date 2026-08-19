"""Tests for the strategy ranking API surface (Module 6).

Route → service → context builder → fakes, with the real ranking algorithm
(no LLM, no network, no Supabase). Covers: 401 unauthenticated, 200 with
ranked strategies, 422 request validation, 404 foreign/missing scans and
unknown targets, 409 non-completed scans, baseline vs contextual, and the
no-secrets guarantee.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.context.services import ContextBuilderService
from app.dependencies.auth import get_current_user
from app.dependencies.rankings import get_ranking_service
from app.evaluations.models import StrategyEvaluation
from app.main import create_app
from app.rankings.services import StrategyRankingService
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.strategies.models import CandidateStrategy
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)
from app.tests.test_strategy_models import make_strategy

USER_A = AuthUser(id="user-a", email="a@example.com", email_verified=True)
USER_B = AuthUser(id="user-b", email="b@example.com", email_verified=True)


def make_issue(rule_id="color-contrast", **overrides):
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


def strategy_payload(issue_id, strategy_id="s-1", **overrides):
    data = make_strategy(strategy_id=strategy_id, issue_id=issue_id, evidence_reference=issue_id)
    data.update(overrides)
    return data


def evaluation_payload(strategy_id, scan_id="scan-1", issue_id="issue-1", **score_overrides):
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
    return {
        "evaluation_id": f"eval-{strategy_id}",
        "strategy_id": strategy_id,
        "scan_id": scan_id,
        "issue_id": issue_id,
        "context_version": "1.0",
        "evaluation_version": "1.0",
        "accessibility_impact_score": scores["accessibility_impact_score"],
        "standards_compliance_score": scores["standards_compliance_score"],
        "contextual_suitability_score": scores["contextual_suitability_score"],
        "implementation_effort_score": scores["implementation_effort_score"],
        "maintainability_score": scores["maintainability_score"],
        "compatibility_score": scores["compatibility_score"],
        "risk_score": scores["risk_score"],
        "strengths": ["A strength."],
        "weaknesses": ["A weakness."],
        "rationale": "A rationale referencing the evidence.",
        "assumptions": [],
        "uncertainties": [],
        "evidence_references": ["issue-1"],
        "evaluator_provider": "mock",
        "evaluator_model": "mock-model",
        "prompt_version": "1.0",
        "evaluated_at": "2026-08-16T00:00:00Z",
    }


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def repo():
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


def _make_service(scans, issues, projects):
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    return StrategyRankingService(context_builder=context_builder)


def _client(repo, user=USER_A, service=None):
    scans, issues, projects = repo
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    resolved = service or _make_service(scans, issues, projects)
    app.dependency_overrides[get_ranking_service] = lambda: resolved
    return TestClient(app)


def _seed_completed(repo, user_id="user-a", status=ScanStatus.COMPLETED):
    scans, issues, projects = repo
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(issues.insert_many(scan.id, [make_issue()]))
    return scan.id


def _body(scan_id, issue_id, strategies, evaluations, mode="contextual"):
    return {
        "issue_id": issue_id,
        "strategy_ids": [s["strategy_id"] for s in strategies],
        "strategies": strategies,
        "evaluations": evaluations,
        "mode": mode,
    }


def test_ranking_requires_authentication(repo):
    client = _client(repo)
    client.app.dependency_overrides[get_current_user] = get_current_user

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000000/ranking",
        json={"issue_id": "x", "strategy_ids": ["s-1", "s-2"], "strategies": [], "evaluations": []},
    )
    assert response.status_code == 401


def test_rank_strategies_baseline(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)]
    evaluations = [evaluation_payload(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2, 3)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, issue_id, strategies, evaluations, mode="baseline"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["issue_id"] == issue_id
    assert body["ranking_method"] == "baseline"
    assert body["ranking_version"] == "1.0"
    assert len(body["ranked_strategies"]) == 3
    assert body["ranked_strategies"][0]["rank"] == 1
    assert "weighted_score" in body["ranked_strategies"][0]
    assert "ranking_explanation" in body["ranked_strategies"][0]
    assert "dimension_scores" in body["ranked_strategies"][0]
    # Weights should sum to approximately 1.0
    weights = body["weights_used"]
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.01


def test_rank_strategies_contextual(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, issue_id, strategies, evaluations, mode="contextual"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ranking_method"] == "contextual"
    assert len(body["context_factors"]) >= 5
    detected = [f for f in body["context_factors"] if f["detected"]]
    assert len(detected) >= 1  # at least one factor detected for SERIOUS issue


def test_ranking_default_mode_is_contextual(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    body = {
        "issue_id": issue_id,
        "strategy_ids": [s["strategy_id"] for s in strategies],
        "strategies": strategies,
        "evaluations": evaluations,
    }
    response = client.post(f"/api/v1/scans/{scan_id}/ranking", json=body)
    assert response.status_code == 200
    assert response.json()["ranking_method"] == "contextual"


def test_request_without_target_422(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json={"strategy_ids": ["s-1", "s-2"], "strategies": strategies, "evaluations": evaluations},
    )
    assert response.status_code == 422


def test_request_empty_strategies_422(repo):
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json={"issue_id": "x", "strategy_ids": [], "strategies": [], "evaluations": []},
    )
    assert response.status_code == 422


def test_strategy_ids_mismatch_422(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [evaluation_payload("s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json={
            "issue_id": issue_id,
            "strategy_ids": ["different-id"],
            "strategies": strategies,
            "evaluations": evaluations,
        },
    )
    assert response.status_code == 422


def test_foreign_scan_404(repo):
    scan_id = _seed_completed(repo, user_id="user-b")
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, "x", strategies, evaluations),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_missing_scan_404(repo):
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}") for i in (1, 2)]

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000001/ranking",
        json=_body("00000000-0000-0000-0000-000000000001", "x", strategies, evaluations),
    )
    assert response.status_code == 404


def test_unknown_target_404(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    client = _client(repo)
    strategies = [strategy_payload("no-such", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, "no-such", strategies, evaluations),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ranking_target_not_found"


def test_running_scan_409(repo):
    scan_id = _seed_completed(repo, status=ScanStatus.RUNNING)
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, "x", strategies, evaluations),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "context_unavailable"


def test_response_has_no_secrets(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    body = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, issue_id, strategies, evaluations),
    ).json()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_ranking_has_recommended_strategy_language(repo):
    """The first-ranked strategy should have rank=1."""
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [evaluation_payload(f"s-{i}", scan_id=scan_id, issue_id=issue_id) for i in (1, 2)]

    body = client.post(
        f"/api/v1/scans/{scan_id}/ranking",
        json=_body(scan_id, issue_id, strategies, evaluations),
    ).json()

    first = body["ranked_strategies"][0]
    assert first["rank"] == 1
    assert first["weighted_score"] >= 0
