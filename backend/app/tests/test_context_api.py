"""Tests for the context API surface.

Route → service → repository stack exercised end-to-end with in-memory fakes
(same convention as ``test_projects.py`` / ``test_scans_api.py``): JWT
dependency overridden, real ContextBuilderService on the fakes.

Covers: 401 unauthenticated, 200 valid context, 404 foreign/missing scans,
409 for non-completed scans, 422 malformed id, and the no-secrets guarantee.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.context.services import ContextBuilderService
from app.dependencies.auth import get_current_user
from app.dependencies.context import get_context_service
from app.main import create_app
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)

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
        "html_snippet": '<p class="muted">Low contrast</p>',
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


@pytest.fixture
def repo() -> tuple[FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    return FakeScanRepository(), FakeIssueRepository(), FakeProjectRepository()


def _client(
    scans: FakeScanRepository,
    issues: FakeIssueRepository,
    projects: FakeProjectRepository,
    user: AuthUser = USER_A,
) -> TestClient:
    app = create_app()
    service = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_context_service] = lambda: service
    return TestClient(app)


def _seed_completed_scan(scans, issues, projects, user_id: str = "user-a") -> str:
    project = projects.seed(user_id)
    scan = scans.seed(user_id, project_id=project.id)
    asyncio.run(issues.insert_many(scan.id, [make_issue()]))
    return scan.id


def test_context_endpoint_requires_authentication(repo) -> None:
    scans, issues, projects = repo
    client = _client(scans, issues, projects)
    client.app.dependency_overrides[get_current_user] = get_current_user

    response = client.get("/api/v1/scans/00000000-0000-0000-0000-000000000000/context")

    assert response.status_code == 401


def test_context_endpoint_returns_document(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed_scan(scans, issues, projects)
    client = _client(scans, issues, projects)

    response = client.get(f"/api/v1/scans/{scan_id}/context")

    assert response.status_code == 200
    body = response.json()
    assert body["context_version"] == "1.0"
    assert body["project"]["name"] == "Seed"
    assert body["project"]["website_url"] == "https://example.com"
    assert body["scan"]["scan_id"] == scan_id
    assert body["scan"]["status"] == "COMPLETED"
    assert body["page"]["hostname"] == "example.com"
    assert len(body["issues"]) == 1
    assert body["issues"][0]["rule"]["rule_id"] == "color-contrast"
    assert body["issues"][0]["wcag"]["criteria"] == ["1.4.3"]
    assert body["issues"][0]["element"]["tag"] == "p"
    group_ids = {g["group_id"] for g in body["groups"]}
    assert "rule:color-contrast" in group_ids
    assert "element:#main > p" in group_ids
    assert "wcag:1.4.3" in group_ids


def test_context_contains_no_user_identity(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed_scan(scans, issues, projects)
    client = _client(scans, issues, projects)

    body = client.get(f"/api/v1/scans/{scan_id}/context").json()

    def walk(node, path: str = "") -> list:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = key.lower()
                if "user" in lowered or "secret" in lowered or "token" in lowered or "password" in lowered:
                    found.append(f"{path}.{key}")
                found.extend(walk(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                found.extend(walk(item, f"{path}[{index}]"))
        return found

    assert walk(body) == []


def test_context_foreign_scan_404(repo) -> None:
    scans, issues, projects = repo
    scan_id = _seed_completed_scan(scans, issues, projects, user_id="user-b")
    client = _client(scans, issues, projects)  # acts as user-a

    response = client.get(f"/api/v1/scans/{scan_id}/context")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_context_missing_scan_404(repo) -> None:
    scans, issues, projects = repo
    client = _client(scans, issues, projects)

    response = client.get("/api/v1/scans/00000000-0000-0000-0000-000000000001/context")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_context_unavailable_for_running_scan(repo) -> None:
    scans, issues, projects = repo
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id, status=ScanStatus.RUNNING)
    client = _client(scans, issues, projects)

    response = client.get(f"/api/v1/scans/{scan.id}/context")

    assert response.status_code == 409
    assert response.json()["code"] == "context_unavailable"


def test_context_malformed_scan_id_422(repo) -> None:
    scans, issues, projects = repo
    client = _client(scans, issues, projects)

    response = client.get("/api/v1/scans/not-a-uuid/context")

    assert response.status_code == 422
