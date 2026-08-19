"""Tests for the scan API surface.

Route → schema → service → repository stack is exercised end-to-end with
in-memory fakes (same convention as ``test_projects.py``): authentication is
replaced via dependency overrides, the service uses the fakes, and the
scanner factory is patched with a deterministic fake engine.

Because TestClient runs FastAPI background tasks before the response returns,
a successful ``POST .../scan`` will already be COMPLETED when the following
``GET`` calls run — which doubles as a live check of the whole pipeline.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.scans import get_scan_service
from app.main import create_app
from app.scans.services import ScanExecutionService
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)

USER_A = AuthUser(id="user-a", email="a@example.com", email_verified=True)
USER_B = AuthUser(id="user-b", email="b@example.com", email_verified=True)


class FakeScanner:
    """Deterministic engine returned by the patched factory."""

    name = "fake-scanner"
    version = "1.0.0"
    wcag_version = "2.2"
    scanner_type = "AXE"

    async def scan(self, url: str, *, depth: int = 1):
        from app.scanners.models import (
            AccessibilityIssue,
            Impact,
            NormalizedScanResult,
            ScanMetadata,
            ScannerType,
            ScanTiming,
            WcagLevel,
        )

        return NormalizedScanResult(
            metadata=ScanMetadata(
                scanner_name=self.name,
                scanner_type=ScannerType.AXE,
                scanner_version=self.version,
                wcag_version=self.wcag_version,
                scan_url=url,
                scan_depth=depth,
                pages_scanned=1,
                browser_name="chromium",
                browser_version="128.0.0.0",
                user_agent="fake",
                total_dom_elements=10,
                tested_elements=1,
            ),
            timing=ScanTiming(duration_ms=500, normalization_duration_ms=10),
            issues=[
                AccessibilityIssue(
                    rule_id="color-contrast",
                    rule_name="Elements must have sufficient color contrast",
                    impact=Impact.SERIOUS,
                    wcag_level=WcagLevel.AA,
                    tags=["wcag2aa"],
                    element_selector="#main > p",
                    html_snippet="<p>low contrast</p>",
                    failure_summary="Fix the contrast",
                )
            ],
        )


@pytest.fixture
def repo(monkeypatch) -> tuple[FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    scans = FakeScanRepository()
    issues = FakeIssueRepository()
    projects = FakeProjectRepository()
    monkeypatch.setattr("app.scans.services.get_scanner", lambda t: FakeScanner())
    return scans, issues, projects


def _client(
    scans: FakeScanRepository,
    issues: FakeIssueRepository,
    projects: FakeProjectRepository,
    user: AuthUser = USER_A,
) -> TestClient:
    app = create_app()
    service = ScanExecutionService(scans=scans, issues=issues, projects=projects)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_scan_service] = lambda: service
    return TestClient(app)


# --- authentication ---------------------------------------------------------


def test_scan_endpoints_require_authentication(repo) -> None:
    scans, issues, projects = repo
    client = _client(scans, issues, projects)
    client.app.dependency_overrides[get_current_user] = get_current_user

    pid = str(uuid4())
    sid = str(uuid4())
    assert client.post(f"/api/v1/projects/{pid}/scan", json={}).status_code == 401
    assert client.get(f"/api/v1/projects/{pid}/scans").status_code == 401
    assert client.get("/api/v1/scans").status_code == 401
    assert client.get(f"/api/v1/scans/{sid}").status_code == 401
    assert client.get(f"/api/v1/scans/{sid}/issues").status_code == 401
    assert client.delete(f"/api/v1/scans/{sid}").status_code == 401


# --- POST /projects/{id}/scan ------------------------------------------------


def test_start_scan_returns_running_scan(repo) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-a")
    client = _client(scans, projects=projects, issues=repo[1])

    response = client.post(f"/api/v1/projects/{project.id}/scan", json={})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["project_id"] == project.id
    assert body["scanner_type"] == "AXE"
    assert body["scan_url"] == "https://example.com"
    assert body["started_at"] is not None
    assert "user_id" not in body


def test_start_scan_background_task_completes_it(repo) -> None:
    scans, issues, projects = repo
    project = projects.seed("user-a")
    client = _client(scans, issues, projects)

    started = client.post(f"/api/v1/projects/{project.id}/scan", json={})
    scan_id = started.json()["id"]

    completed = client.get(f"/api/v1/scans/{scan_id}")

    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["total_issues"] == 1
    assert completed.json()["serious_count"] == 1
    assert completed.json()["accessibility_score"] == 95.0
    assert completed.json()["scanner_name"] == "fake-scanner"

    issues_response = client.get(f"/api/v1/scans/{scan_id}/issues")
    assert issues_response.status_code == 200
    assert len(issues_response.json()) == 1
    issue = issues_response.json()[0]
    assert issue["rule_id"] == "color-contrast"
    assert issue["impact"] == "SERIOUS"
    assert issue["scan_id"] == scan_id


def test_start_scan_foreign_project_404(repo) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-b")
    client = _client(scans, projects=projects, issues=repo[1])

    response = client.post(f"/api/v1/projects/{project.id}/scan", json={})

    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"


def test_start_scan_rejects_unknown_scanner_type(repo) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-a")
    client = _client(scans, projects=projects, issues=repo[1])

    response = client.post(
        f"/api/v1/projects/{project.id}/scan", json={"scanner_type": "GHOST"}
    )

    assert response.status_code == 422


def test_start_scan_unregistered_scanner_503(repo, monkeypatch) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-a")
    client = _client(scans, projects=projects, issues=repo[1])

    from app.scanners.factory import ScannerUnavailableError

    def _unavailable(t):
        raise ScannerUnavailableError("No scanner engine is registered for LIGHTHOUSE.")

    monkeypatch.setattr("app.scans.services.get_scanner", _unavailable)

    response = client.post(
        f"/api/v1/projects/{project.id}/scan",
        json={"scanner_type": "LIGHTHOUSE"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "scan_configuration_error"


def test_start_scan_malformed_project_id_422(repo) -> None:
    scans, _issues, projects = repo
    client = _client(scans, projects=projects, issues=repo[1])

    response = client.post("/api/v1/projects/not-a-uuid/scan", json={})

    assert response.status_code == 422


# --- GET scans ----------------------------------------------------------------


def test_list_scans_returns_only_own(repo) -> None:
    scans, _issues, _projects = repo
    scans.seed("user-a", project_id="p-a")
    scans.seed("user-a", project_id="p-a")
    scans.seed("user-b", project_id="p-b")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get("/api/v1/scans")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert all(row["project_id"] == "p-a" for row in rows)
    assert all("user_id" not in row for row in rows)


def test_get_own_scan(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-a")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get(f"/api/v1/scans/{scan.id}")

    assert response.status_code == 200
    assert response.json()["id"] == scan.id
    assert "user_id" not in response.json()


def test_get_foreign_scan_404(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-b")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get(f"/api/v1/scans/{scan.id}")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_get_missing_scan_404(repo) -> None:
    scans, _issues, _projects = repo
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get(f"/api/v1/scans/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_get_foreign_scan_issues_404(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-b")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get(f"/api/v1/scans/{scan.id}/issues")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"


def test_get_issues_empty_scan(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-a")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.get(f"/api/v1/scans/{scan.id}/issues")

    assert response.status_code == 200
    assert response.json() == []


# --- GET /projects/{id}/scans -------------------------------------------------


def test_list_project_scans(repo) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-a")
    scans.seed("user-a", project_id=project.id)
    scans.seed("user-a", project_id=project.id)
    scans.seed("user-a", project_id="other-project")
    client = _client(scans, issues=repo[1], projects=projects)

    response = client.get(f"/api/v1/projects/{project.id}/scans")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert all(row["project_id"] == project.id for row in rows)


def test_list_foreign_project_scans_404(repo) -> None:
    scans, _issues, projects = repo
    project = projects.seed("user-b")
    client = _client(scans, issues=repo[1], projects=projects)

    response = client.get(f"/api/v1/projects/{project.id}/scans")

    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"


# --- DELETE /scans/{id} --------------------------------------------------------


def test_delete_own_scan(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-a")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.delete(f"/api/v1/scans/{scan.id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/scans/{scan.id}").status_code == 404


def test_delete_foreign_scan_404(repo) -> None:
    scans, _issues, _projects = repo
    scan = scans.seed("user-b")
    client = _client(scans, issues=repo[1], projects=repo[2])

    response = client.delete(f"/api/v1/scans/{scan.id}")

    assert response.status_code == 404
    assert response.json()["code"] == "scan_not_found"
