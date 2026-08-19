"""Tests for the Supabase PostgREST scan repository.

The PostgREST HTTP calls are replaced with a fake transport (same convention
as the project repository and auth provider tests) so the repository is
exercised without network access or real credentials.
"""

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.scans.exceptions import ScanConfigurationError, ScanError
from app.scans.models import Scan, ScanCreate, ScanStatus, ScanUpdate
from app.scanners.models import ScannerType
from app.repositories.scans import SupabaseScanRepository

ROW = {
    "id": "scan-1",
    "project_id": "project-1",
    "user_id": "user-a",
    "scanner_type": "AXE",
    "status": "PENDING",
    "started_at": None,
    "completed_at": None,
    "duration_ms": None,
    "summary": {},
    "total_issues": 0,
    "critical_count": 0,
    "serious_count": 0,
    "moderate_count": 0,
    "minor_count": 0,
    "accessibility_score": None,
    "scanner_name": None,
    "scanner_version": None,
    "wcag_version": None,
    "scan_url": "https://example.com",
    "scan_depth": 1,
    "pages_scanned": 0,
    "browser_name": None,
    "browser_version": None,
    "user_agent": None,
    "total_dom_elements": 0,
    "tested_elements": 0,
    "normalization_duration_ms": None,
    "persistence_duration_ms": None,
    "created_at": "2026-08-14T10:00:00+00:00",
}


def _settings(**overrides) -> Settings:
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-role-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _repo(**settings_overrides) -> SupabaseScanRepository:
    return SupabaseScanRepository(_settings(**settings_overrides))


class FakeResponse:
    def __init__(self, status_code: int, json_data) -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


class FakeAsyncClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    async def patch(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("patch", url, kwargs))
        return self.responses.pop(0)

    async def delete(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("delete", url, kwargs))
        return self.responses.pop(0)


def _patch_http(monkeypatch, *responses) -> FakeAsyncClient:
    client = FakeAsyncClient(responses)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    return client


def test_create_posts_row_to_postgrest(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(201, [ROW]))

    scan = asyncio.run(
        repo.create(
            ScanCreate(
                user_id="user-a",
                project_id="project-1",
                scanner_type=ScannerType.AXE,
                scan_url="https://example.com",
            )
        )
    )

    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/rest/v1/scans"
    assert kwargs["headers"]["apikey"] == "service-role-key"
    assert kwargs["headers"]["Authorization"] == "Bearer service-role-key"
    assert kwargs["headers"]["Prefer"] == "return=representation"
    assert kwargs["json"] == {
        "project_id": "project-1",
        "user_id": "user-a",
        "scanner_type": "AXE",
        "status": "PENDING",
        "scan_url": "https://example.com",
    }
    assert isinstance(scan, Scan)
    assert scan.id == "scan-1"
    assert scan.user_id == "user-a"
    assert scan.project_id == "project-1"
    assert scan.status == ScanStatus.PENDING


def test_create_maps_full_row_including_metadata(monkeypatch) -> None:
    completed = {
        **ROW,
        "status": "COMPLETED",
        "scanner_name": "axe-core",
        "scanner_version": "4.10.2",
        "wcag_version": "2.2",
        "total_issues": 3,
        "critical_count": 1,
        "summary": {"total_issues": 3, "critical_count": 1},
        "accessibility_score": 72.5,
    }
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(201, [completed]))

    scan = asyncio.run(
        repo.create(ScanCreate(user_id="user-a", project_id="project-1", scanner_type=ScannerType.AXE))
    )

    assert scan.status == ScanStatus.COMPLETED
    assert scan.scanner_name == "axe-core"
    assert scan.wcag_version == "2.2"
    assert scan.total_issues == 3
    assert scan.critical_count == 1
    assert scan.accessibility_score == 72.5
    assert scan.summary == {"total_issues": 3, "critical_count": 1}


def test_get_returns_scan_when_found(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    scan = asyncio.run(repo.get("user-a", "scan-1"))

    assert scan is not None
    assert scan.id == "scan-1"


def test_get_returns_none_when_empty(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, []))

    scan = asyncio.run(repo.get("user-a", "scan-1"))

    assert scan is None


def test_get_scopes_query_to_user(monkeypatch) -> None:
    """Ownership is enforced in the query itself — the repository never asks
    for a scan without also filtering by the caller."""
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, []))

    asyncio.run(repo.get("user-a", "scan-1"))

    params = client.calls[0][2]["params"]
    assert params["user_id"] == "eq.user-a"
    assert params["id"] == "eq.scan-1"


def test_list_for_project_filters_owner_and_project(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    scans = asyncio.run(repo.list_for_project("user-a", "project-1"))

    method, url, kwargs = client.calls[0]
    assert method == "get"
    assert kwargs["params"] == {
        "user_id": "eq.user-a",
        "project_id": "eq.project-1",
        "order": "created_at.desc",
        "select": "*",
    }
    assert len(scans) == 1
    assert scans[0].project_id == "project-1"


def test_list_for_user_filters_owner(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    scans = asyncio.run(repo.list_for_user("user-a"))

    params = client.calls[0][2]["params"]
    assert params["user_id"] == "eq.user-a"
    assert "project_id" not in params
    assert params["order"] == "created_at.desc"
    assert len(scans) == 1


def test_update_sends_changes_and_returns_row(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(
        monkeypatch,
        FakeResponse(200, [{**ROW, "status": "RUNNING"}]),
    )

    scan = asyncio.run(
        repo.update("user-a", "scan-1", ScanUpdate(status=ScanStatus.RUNNING))
    )

    method, url, kwargs = client.calls[0]
    assert method == "patch"
    assert kwargs["params"] == {
        "id": "eq.scan-1",
        "user_id": "eq.user-a",
        "select": "*",
    }
    assert kwargs["json"] == {"status": "RUNNING"}
    assert scan is not None
    assert scan.status == ScanStatus.RUNNING


def test_update_returns_none_when_not_found(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, []))

    scan = asyncio.run(
        repo.update("user-a", "scan-1", ScanUpdate(status=ScanStatus.COMPLETED))
    )

    assert scan is None


def test_update_with_empty_changes_falls_back_to_get(monkeypatch) -> None:
    """A no-op PATCH resolves to the current row rather than an empty PATCH."""
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    scan = asyncio.run(repo.update("user-a", "scan-1", ScanUpdate()))

    assert scan is not None
    assert scan.id == "scan-1"


def test_delete_returns_true_when_row_removed(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    deleted = asyncio.run(repo.delete("user-a", "scan-1"))

    assert deleted is True


def test_delete_returns_false_when_no_row_matched(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, []))

    deleted = asyncio.run(repo.delete("user-a", "scan-1"))

    assert deleted is False
    params = client.calls[0][2]["params"]
    assert params["user_id"] == "eq.user-a"
    assert params["id"] == "eq.scan-1"


def test_repository_requires_configuration_before_network(monkeypatch) -> None:
    repo = _repo(supabase_url="", supabase_service_role_key="")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("no network"))

    with pytest.raises(ScanConfigurationError):
        asyncio.run(
            repo.create(
                ScanCreate(user_id="user-a", project_id="project-1", scanner_type=ScannerType.AXE)
            )
        )

    with pytest.raises(ScanConfigurationError):
        asyncio.run(repo.list_for_user("user-a"))


def test_repository_maps_postgrest_errors(monkeypatch) -> None:
    repo = _repo()
    _patch_http(
        monkeypatch,
        FakeResponse(
            400,
            {"code": "PGRST200", "message": "Could not parse the request body", "details": "..."},
        ),
    )

    with pytest.raises(ScanError) as excinfo:
        asyncio.run(
            repo.create(
                ScanCreate(user_id="user-a", project_id="project-1", scanner_type=ScannerType.AXE)
            )
        )

    assert "Could not parse the request body" in str(excinfo.value)
    assert "service-role-key" not in str(excinfo.value)


def test_row_mapping_accepts_trimmed_fractional_seconds(monkeypatch) -> None:
    """PostgREST trims trailing zeros in fractional seconds (``.874710`` →
    ``.87471``); the mapper must tolerate the 5-digit form (Python 3.9's
    ``fromisoformat`` otherwise rejects it)."""
    repo = _repo()
    row = {**ROW, "created_at": "2026-08-14T10:00:00.87471+00:00"}
    _patch_http(monkeypatch, FakeResponse(200, [row]))

    scan = asyncio.run(repo.get("user-a", "scan-1"))

    assert scan is not None
    assert scan.created_at.microsecond == 874710


def test_row_mapping_never_leaks_ownership_fields_outside_model(monkeypatch) -> None:
    """The mapped Scan carries ownership internally but the repository layer
    always receives the owner explicitly — never from a stored row."""
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    scan = asyncio.run(repo.get("user-a", "scan-1"))

    assert scan.user_id == "user-a"  # retained for internal scoping/auditing
    assert scan.project_id == "project-1"
