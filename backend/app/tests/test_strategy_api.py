"""Tests for the strategy generation API surface.

Route → service → context builder → fakes, with the mock provider (no LLM,
no network, no Supabase). Covers: 401 unauthenticated, 200 with metadata +
2–5 strategies, 422 request validation, 404 foreign/missing scans and
unknown targets, 409 non-completed scans, 503 missing LLM configuration,
502 invalid provider output, and the no-secrets guarantee.
"""

import asyncio
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.context.services import ContextBuilderService
from app.core.config import Settings
from app.dependencies.auth import get_current_user
from app.dependencies.strategies import get_strategy_provider, get_strategy_service
from app.main import create_app
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.strategies.exceptions import (
    StrategyConfigurationError,
    StrategyOutputError,
)
from app.strategies.models import CandidateStrategy, StrategyGenerationRequest
from app.strategies.providers.mock import MockStrategyProvider
from app.strategies.services import StrategyGenerationService
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


def run(coro):
    return asyncio.run(coro)


class BoomProvider:
    """Provider that fails with a fixed exception (injected via DI override)."""

    name = "boom"

    def __init__(self, error) -> None:
        self._error = error

    async def generate(self, request: StrategyGenerationRequest) -> List[CandidateStrategy]:
        raise self._error


@pytest.fixture
def repo() -> tuple[FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


def _make_service(
    scans: FakeScanRepository,
    issues: FakeIssueRepository,
    projects: FakeProjectRepository,
    provider=None,
) -> StrategyGenerationService:
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    settings = Settings(llm_provider="mock", llm_model="mock-model")
    return StrategyGenerationService(
        context_builder=context_builder,
        provider=provider or MockStrategyProvider(settings),
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
        app.dependency_overrides[get_strategy_provider] = service
    else:
        resolved = service or _make_service(scans, issues, projects)
        app.dependency_overrides[get_strategy_service] = lambda: resolved
    return TestClient(app)


def _seed_completed(repo, user_id: str = "user-a", status: ScanStatus = ScanStatus.COMPLETED) -> str:
    scans, issues, projects = repo
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(issues.insert_many(scan.id, [make_issue()]))
    return scan.id


def test_strategies_requires_authentication(repo) -> None:
    client = _client(repo)
    client.app.dependency_overrides[get_current_user] = get_current_user

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000000/strategies",
        json={"issue_id": "x"},
    )

    assert response.status_code == 401


def test_generate_strategies_for_issue(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies",
        json={"issue_id": issue_id},
    )

    assert response.status_code == 200
    body = response.json()
    metadata = body["metadata"]
    assert metadata["scan_id"] == scan_id
    assert metadata["target_type"] == "issue"
    assert metadata["issue_id"] == issue_id
    assert metadata["context_version"] == "1.0"
    assert metadata["prompt_version"] == "1.0"
    assert metadata["provider"] == "mock"
    assert metadata["strategy_count"] == 3
    strategies = body["strategies"]
    assert len(strategies) == 3
    assert {s["strategy_index"] for s in strategies} == {1, 2, 3}
    assert all(s["issue_id"] == issue_id for s in strategies)
    assert all(s["evidence_reference"] == issue_id for s in strategies)


def test_generate_with_custom_count(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies",
        json={"issue_id": issue_id, "strategy_count": 5},
    )

    assert response.status_code == 200
    assert len(response.json()["strategies"]) == 5
    assert response.json()["metadata"]["strategy_count"] == 5


def test_generate_for_group(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    client = _client(repo)
    context = run(
        ContextBuilderService(
            scans=scans, issues=issues, projects=_projects
        ).build_for_scan("user-a", scan_id)
    )
    group = next(g for g in context.groups if g.group_type == "same_rule")

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies",
        json={"group_id": group.group_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["target_type"] == "group"
    assert body["metadata"]["group_id"] == group.group_id
    assert all(s["group_id"] == group.group_id for s in body["strategies"])


def test_request_without_target_422(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(f"/api/v1/scans/{scan_id}/strategies", json={})

    assert response.status_code == 422


def test_request_count_out_of_range_422(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(repo)

    for bad in (1, 6):
        response = client.post(
            f"/api/v1/scans/{scan_id}/strategies",
            json={"issue_id": "x", "strategy_count": bad},
        )
        assert response.status_code == 422


def test_foreign_scan_404(repo) -> None:
    scan_id = _seed_completed(repo, user_id="user-b")
    client = _client(repo)  # acts as user-a

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": "x"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_missing_scan_404(repo) -> None:
    client = _client(repo)

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000001/strategies",
        json={"issue_id": "x"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_unknown_issue_404(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": "no-such-issue"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "strategy_target_not_found"


def test_unknown_group_404(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"group_id": "rule:no-such"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "strategy_target_not_found"


def test_running_scan_409(repo) -> None:
    scan_id = _seed_completed(repo, status=ScanStatus.RUNNING)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": "x"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "context_unavailable"


def test_missing_llm_config_503(repo) -> None:
    scan_id = _seed_completed(repo)
    client = _client(
        repo,
        service=lambda: (_ for _ in ()).throw(
            StrategyConfigurationError("LLM_API_KEY is not configured.")
        ),
        override_provider=True,
    )

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": "x"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "strategy_configuration_error"


def test_invalid_provider_output_502(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    service = _make_service(scans, issues, projects, provider=BoomProvider(StrategyOutputError("bad")))
    client = _client(repo, service=service)

    response = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": issue_id}
    )

    assert response.status_code == 502
    assert response.json()["code"] == "strategy_output_invalid"


def test_response_contains_no_secrets(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)

    body = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": issue_id}
    ).json()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_no_best_strategy_wording(repo) -> None:
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)

    body = client.post(
        f"/api/v1/scans/{scan_id}/strategies", json={"issue_id": issue_id}
    ).json()

    serialized = str(body).lower()
    for forbidden in ("best strategy", "recommended strategy", "optimal strategy", "use this strategy"):
        assert forbidden not in serialized
