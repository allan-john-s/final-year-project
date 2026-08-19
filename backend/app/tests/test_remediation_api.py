"""Tests for the remediation API surface (Module 7).

Covers: 401 unauthenticated, 200 with generated proposals, 422 validation,
404 foreign/missing scans, 409 non-recommended strategy and invalid transitions,
proposal retrieval, status updates, and the no-secrets guarantee.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.context.services import ContextBuilderService
from app.dependencies.auth import get_current_user
from app.dependencies.remediations import get_remediation_service
from app.main import create_app
from app.remediations.models import RemediationStatus
from app.remediations.providers.mock import MockRemediationProvider
from app.remediations.services import RemediationService
from app.remediations.store import RemediationStore, get_remediation_store
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
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


def run(coro):
    return asyncio.run(coro)


def _eval_payload(strategy_id, scan_id, issue_id, **score_overrides):
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
        **scores,
        "strengths": ["Effective approach."],
        "weaknesses": ["Minor concern."],
        "rationale": "A rationale referencing the evidence.",
        "assumptions": [],
        "uncertainties": [],
        "evidence_references": [issue_id],
        "evaluator_provider": "mock",
        "evaluator_model": "mock-model",
        "prompt_version": "1.0",
    }


@pytest.fixture
def repo():
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


def _make_service(scans, issues, projects):
    context_builder = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    return RemediationService(context_builder=context_builder, provider=MockRemediationProvider())


def _client(repo, user=USER_A, service=None, store=None):
    scans, issues, projects = repo
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    resolved = service or _make_service(scans, issues, projects)
    app.dependency_overrides[get_remediation_service] = lambda: resolved
    # Use a shared store instance for the test (not a new one per call)
    shared_store = store if store is not None else RemediationStore()
    app.dependency_overrides[get_remediation_store] = lambda: shared_store
    return TestClient(app)


def _seed_completed(repo, user_id="user-a", status=ScanStatus.COMPLETED):
    scans, issues, projects = repo
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id, status=status)
    run(issues.insert_many(scan.id, [make_issue()]))
    return scan.id


def _remediation_body(issue_id, strategies, evaluations, strategy_id="s-1"):
    return {
        "issue_id": issue_id,
        "strategy_id": strategy_id,
        "strategies": strategies,
        "evaluations": evaluations,
    }


# --- authentication --------------------------------------------------------


def test_remediation_requires_authentication(repo):
    client = _client(repo)
    client.app.dependency_overrides[get_current_user] = get_current_user

    response = client.post(
        "/api/v1/scans/00000000-0000-0000-0000-000000000000/remediation",
        json={"issue_id": "x", "strategy_id": "s-1", "strategies": [], "evaluations": []},
    )
    assert response.status_code == 401


# --- generation ------------------------------------------------------------


def test_generate_remediation(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [_eval_payload(f"s-{i}", scan_id, issue_id) for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == scan_id
    assert body["issue_id"] == issue_id
    assert body["strategy_id"] == "s-1"
    assert body["status"] == "PROPOSED"
    assert body["title"]
    assert body["summary"]
    assert body["proposed_change"]["before"]
    assert body["proposed_change"]["after"]
    assert body["implementation_steps"]
    assert body["validation_steps"]
    assert 0 <= body["confidence"] <= 1


def test_generate_remediation_rejects_non_recommended(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [
        _eval_payload("s-1", scan_id, issue_id,
                       accessibility_impact_score=10, standards_compliance_score=10,
                       contextual_suitability_score=10, implementation_effort_score=10,
                       maintainability_score=10, compatibility_score=10, risk_score=10),
        _eval_payload("s-2", scan_id, issue_id,
                       accessibility_impact_score=2, standards_compliance_score=2,
                       contextual_suitability_score=2, implementation_effort_score=2,
                       maintainability_score=2, compatibility_score=2, risk_score=2),
    ]

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations, strategy_id="s-2"),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "strategy_not_recommended"


# --- request validation ----------------------------------------------------


def test_request_missing_fields_422(repo):
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json={"issue_id": "x"},
    )
    assert response.status_code == 422


def test_request_empty_strategies_422(repo):
    scan_id = _seed_completed(repo)
    client = _client(repo)

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json={"issue_id": "x", "strategy_id": "s-1", "strategies": [], "evaluations": []},
    )
    assert response.status_code == 422


# --- ownership ------------------------------------------------------------


def test_foreign_scan_404(repo):
    scan_id = _seed_completed(repo, user_id="user-b")
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [_eval_payload(f"s-{i}", scan_id, "x") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body("x", strategies, evaluations),
    )
    assert response.status_code == 404


def test_running_scan_409(repo):
    scan_id = _seed_completed(repo, status=ScanStatus.RUNNING)
    client = _client(repo)
    strategies = [strategy_payload("x", strategy_id=f"s-{i}") for i in (1, 2)]
    evaluations = [_eval_payload(f"s-{i}", scan_id, "x") for i in (1, 2)]

    response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body("x", strategies, evaluations),
    )
    assert response.status_code == 409


# --- retrieval and status updates ------------------------------------------


def test_get_remediation_by_id(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [_eval_payload("s-1", scan_id, issue_id)]

    gen_response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    )
    assert gen_response.status_code == 200
    proposal_id = gen_response.json()["id"]

    get_response = client.get(f"/api/v1/remediations/{proposal_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == proposal_id


def test_get_nonexistent_remediation_404(repo):
    client = _client(repo)
    response = client.get("/api/v1/remediations/nonexistent-id")
    assert response.status_code == 404


def test_list_remediations_for_scan(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [_eval_payload("s-1", scan_id, issue_id)]

    client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    )

    list_response = client.get(f"/api/v1/scans/{scan_id}/remediations")
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) >= 1


def test_update_status_valid_transition(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [_eval_payload("s-1", scan_id, issue_id)]

    gen_response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    )
    proposal_id = gen_response.json()["id"]
    assert gen_response.json()["status"] == "PROPOSED"

    # PROPOSED -> REVIEWED
    patch_response = client.patch(
        f"/api/v1/remediations/{proposal_id}/status",
        json={"status": "REVIEWED"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "REVIEWED"

    # REVIEWED -> ACCEPTED
    patch_response = client.patch(
        f"/api/v1/remediations/{proposal_id}/status",
        json={"status": "ACCEPTED"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "ACCEPTED"


def test_update_status_invalid_transition(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [_eval_payload("s-1", scan_id, issue_id)]

    gen_response = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    )
    proposal_id = gen_response.json()["id"]

    # PROPOSED -> ACCEPTED is invalid (must go through REVIEWED)
    patch_response = client.patch(
        f"/api/v1/remediations/{proposal_id}/status",
        json={"status": "ACCEPTED"},
    )
    assert patch_response.status_code == 409


# --- no secrets ------------------------------------------------------------


def test_response_has_no_secrets(repo):
    scans, issues, _projects = repo
    scan_id = _seed_completed(repo)
    issue_id = issues.issues_for(scan_id)[0].id
    client = _client(repo)
    strategies = [strategy_payload(issue_id, strategy_id="s-1")]
    evaluations = [_eval_payload("s-1", scan_id, issue_id)]

    body = client.post(
        f"/api/v1/scans/{scan_id}/remediation",
        json=_remediation_body(issue_id, strategies, evaluations),
    ).json()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized
