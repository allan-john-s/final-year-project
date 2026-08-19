"""Tests for the strategy evaluation API surface.

Route → service → context builder → fakes, with the mock evaluator (no LLM,
no network, no Supabase). Covers: 401 unauthenticated, 200 with one
independent 7-dimensional evaluation per strategy, 422 request/strategy
validation, 404 foreign/missing scans and unknown targets, 409 non-completed
scans, 503 missing LLM configuration, 502 invalid provider output, and the
no-total/no-rank/no-secrets guarantees.
"""

import asyncio
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.context.services import ContextBuilderService
from app.core.config import Settings
from app.dependencies.auth import get_current_user
from app.dependencies.evaluations import (
    get_evaluation_provider,
    get_evaluation_service,
)
from app.evaluations.exceptions import (
    EvaluationConfigurationError,
    EvaluationProviderError,
)
from app.evaluations.models import (
    EvaluationDraft,
    StrategyEvaluationRequest,
)
from app.evaluations.providers.mock import MockEvaluationProvider
from app.evaluations.services import StrategyEvaluationService
from app.main import create_app
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


def make_issue(rule_id: str = "color-contrast", **overrides) -> AccessibilityIssue:
    defaults = {
        "rule_id": rule_id,
        "rule_name": "Elements must have sufficient color contrast",
        "impact": Impact.SERIOUS,
        "wcag_level": WcagLevel.AA,
        "tags": ["wcag2aa", "wcag143"],
        "element_selector": "#main > p",
        "html_snippet": '<p class="muted">Low contrast text</p>',
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


def strategy_payload(issue_id: str, strategy_id: str = "native-1", **overrides) -> dict:
    data = make_strategy(
        strategy_id=strategy_id,
        issue_id=issue_id,
        evidence_reference=issue_id,
    )
    data.update(overrides)
    return data


def run(coro):
    return asyncio.run(coro)


class BoomProvider:
    """Provider that fails with a fixed exception (injected via DI override)."""

    name = "boom"

    def __init__(self, error) -> None:
        self._error = error

    async def evaluate(self, request: StrategyEvaluationRequest) -> EvaluationDraft:
        raise self._error


@pytest.fixture
def repo() -> tuple[FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


def _make_service(
    scans: FakeScanRepository,
    issues: FakeIssueRepository,
    projects: FakeProjectRepository,
    provider=None,
) -> StrategyEvaluationService:
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    settings = Settings(llm_provider="mock", llm_model="mock-model")
    return StrategyEvaluationService(
        context_builder=context_builder,
        provider=provider or MockEvaluationProvider(settings),
        model="mock-model",
        temperature=0.2,
        max_tokens=1000,
    )


def _client(
    repo: tuple,
    user: AuthUser = USER_A,
    service=None,
    *,
    override_provider=False,
) -> TestClient:
    scans, issues, projects = repo
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    if override_provider:
        app.dependency_overrides[get_evaluation_provider] = service
    else:
        resolved = service or _make_service(scans, issues, projects)
        app.dependency_overrides[get_evaluation_service] = lambda: resolved
    return TestClient(app)


def _seed_completed(repo, user_id: str = "user-a", status: ScanStatus = ScanStatus.COMPLETED) -> str:
    scans, issues, projects = repo
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(issues.insert_many(scan.id, [make_issue()]))
    return scan.id


def _body(scan_id: str, issue_id: str, strategies: List[dict]) -> dict:
    return {
        "issue_id": issue_id,
        "strategy_ids": [s["strategy_id"] for s in strategies],
        "strategies": strategies,
    }


def test_evaluations_requires_authentication(repo) -> None:
    client = _client(repo)
    client.app.dependency_overrides[get_current_user] = get_current_user

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000000/evaluations",
        json={"issue_id": "x", "strategy_ids": ["s-1"], "strategies": []},
    )

    assert response.status_code == 401


def test_evaluate_strategies_for_issue(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [
        strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)
    ]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["issue_id"] == issue_id
    assert body["group_id"] is None
    assert body["context_version"] == "1.0"
    assert body["evaluation_version"] == "1.0"
    assert body["prompt_version"] == "1.0"
    assert body["provider"] == "mock"
    evaluations = body["evaluations"]
    assert len(evaluations) == 3
    for index, evaluation in enumerate(evaluations, start=1):
        assert evaluation["strategy_id"] == f"s-{index}"
        assert evaluation["evaluation_id"] == f"eval-s-{index}"
        assert evaluation["scan_id"] == scan_id
        assert evaluation["issue_id"] == issue_id
        assert evaluation["evaluator_provider"] == "mock"
        assert evaluation["evaluated_at"]
        for field in (
            "accessibility_impact_score",
            "standards_compliance_score",
            "contextual_suitability_score",
            "implementation_effort_score",
            "maintainability_score",
            "compatibility_score",
            "risk_score",
        ):
            assert 0 <= evaluation[field] <= 10
        assert evaluation["strengths"]
        assert evaluation["weaknesses"]
        assert evaluation["rationale"]
        assert evaluation["evidence_references"]


def test_evaluate_single_strategy(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    )

    assert response.status_code == 200
    assert len(response.json()["evaluations"]) == 1


def test_evaluate_for_group(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed(repo)
    client = _client(repo)
    context = run(
        ContextBuilderService(scans=scans, issues=issues, projects=projects).build_for_scan(
            "user-a", scan_id
        )
    )
    group = next(g for g in context.groups if g.group_type == "same_rule")
    primary_issue_id = context.issues[0].issue_id
    strategies = [
        strategy_payload(
            primary_issue_id,
            strategy_id="s-1",
            group_id=group.group_id,
            evidence_reference=group.group_id,
        )
    ]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json={
            "group_id": group.group_id,
            "strategy_ids": ["s-1"],
            "strategies": strategies,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == group.group_id
    assert body["issue_id"] is None
    assert body["evaluations"][0]["group_id"] == group.group_id


def test_request_without_target_422(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json={"strategy_ids": ["s-1"], "strategies": strategies},
    )

    assert response.status_code == 422


def test_request_empty_lists_422(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json={"issue_id": "x", "strategy_ids": [], "strategies": []},
    )

    assert response.status_code == 422


def test_request_strategy_ids_mismatch_422(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json={
            "issue_id": issue_id,
            "strategy_ids": ["different-id"],
            "strategies": strategies,
        },
    )

    assert response.status_code == 422


def test_strategy_not_matching_context_422(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    # strategy claims a different issue than the target
    strategies = [strategy_payload("other-issue", strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "evaluation_strategy_invalid"


def test_foreign_scan_404(repo) -> None:
    scan_id = _seed_completed(repo, user_id="user-b")
    client = _client(repo)  # acts as user-a
    strategies = [strategy_payload("x", strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, "x", strategies),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_missing_scan_404(repo) -> None:
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id="s-1")]

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000001/evaluations",
        json=_body("00000000-0000-0000-0000-000000000001", "x", strategies),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_unknown_target_404(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    client = _client(repo)
    strategies = [strategy_payload("no-such-issue", strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, "no-such-issue", strategies),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "evaluation_target_not_found"


def test_running_scan_409(repo) -> None:
    scan_id = _seed_completed(repo, status=ScanStatus.RUNNING)
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, "x", strategies),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "context_unavailable"


def test_missing_llm_config_503(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(
        repo,
        service=lambda: (_ for _ in ()).throw(
            EvaluationConfigurationError("LLM_API_KEY is not configured.")
        ),
        override_provider=True,
    )
    strategies = [strategy_payload("x", strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, "x", strategies),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "evaluation_configuration_error"


def test_provider_failure_502(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    service = _make_service(
        scans,
        issues,
        projects,
        provider=BoomProvider(EvaluationProviderError("The evaluator is down.")),
    )
    client = _client(repo, service=service)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]

    response = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    )

    assert response.status_code == 502
    assert response.json()["code"] == "evaluation_provider_error"


def test_response_contains_no_secrets(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]

    body = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    ).json()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_no_total_score_no_rank_no_best_wording(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [
        strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2, 3)
    ]

    body = client.post(
        f"/api/v1/scans/{scan_id}/evaluations",
        json=_body(scan_id, issue_id, strategies),
    ).json()

    serialized = str(body).lower()
    assert "total_score" not in serialized
    assert '"rank"' not in serialized
    assert "winner" not in serialized
    for forbidden in ("best strategy", "recommended strategy", "optimal strategy", "use this strategy"):
        assert forbidden not in serialized
