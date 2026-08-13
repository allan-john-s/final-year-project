"""Tests for the Supabase PostgREST project repository.

The PostgREST HTTP calls are replaced with a fake transport (same convention
as the auth provider tests) so the repository is exercised without network
access or real credentials.
"""

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.projects.exceptions import ProjectConfigurationError, ProjectError
from app.projects.models import (
    Project,
    ProjectCreate,
    ProjectStatus,
    ProjectUpdate,
)
from app.repositories.projects import SupabaseProjectRepository

ROW = {
    "id": "p-1",
    "user_id": "user-a",
    "name": "Homepage",
    "description": "Our main site",
    "website_url": "https://example.com",
    "status": "NOT_SCANNED",
    "created_at": "2026-08-13T10:00:00+00:00",
    "updated_at": "2026-08-13T10:00:00+00:00",
}


def _settings(**overrides) -> Settings:
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-role-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _repo(**settings_overrides) -> SupabaseProjectRepository:
    return SupabaseProjectRepository(_settings(**settings_overrides))


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

    project = asyncio.run(
        repo.create(
            ProjectCreate(
                user_id="user-a",
                name="Homepage",
                description="Our main site",
                website_url="https://example.com",
            )
        )
    )

    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/rest/v1/projects"
    assert kwargs["headers"]["apikey"] == "service-role-key"
    assert kwargs["headers"]["Authorization"] == "Bearer service-role-key"
    assert kwargs["headers"]["Prefer"] == "return=representation"
    assert kwargs["json"] == {
        "user_id": "user-a",
        "name": "Homepage",
        "description": "Our main site",
        "website_url": "https://example.com",
        "status": "NOT_SCANNED",
    }
    assert isinstance(project, Project)
    assert project.id == "p-1"
    assert project.user_id == "user-a"
    assert project.status == ProjectStatus.NOT_SCANNED


def test_list_by_user_filters_and_orders(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    projects = asyncio.run(repo.list_by_user("user-a"))

    method, url, kwargs = client.calls[0]
    assert method == "get"
    assert kwargs["params"] == {
        "user_id": "eq.user-a",
        "order": "created_at.desc",
        "select": "*",
    }
    assert len(projects) == 1
    assert projects[0].name == "Homepage"


def test_get_returns_project_when_found(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    project = asyncio.run(repo.get("user-a", "p-1"))

    assert project is not None
    assert project.id == "p-1"


def test_get_returns_none_when_empty(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, []))

    project = asyncio.run(repo.get("user-a", "p-1"))

    assert project is None


def test_get_scopes_query_to_user(monkeypatch) -> None:
    """Ownership is enforced in the query itself — the repository never asks
    for a project without also filtering by the caller."""
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, []))

    asyncio.run(repo.get("user-a", "p-1"))

    params = client.calls[0][2]["params"]
    assert params["user_id"] == "eq.user-a"
    assert params["id"] == "eq.p-1"


def test_update_sends_changes_and_returns_row(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(
        monkeypatch,
        FakeResponse(200, [{**ROW, "name": "Renamed", "status": "SCANNING"}]),
    )

    project = asyncio.run(
        repo.update(
            "user-a",
            "p-1",
            ProjectUpdate(name="Renamed", status=ProjectStatus.SCANNING),
        )
    )

    method, url, kwargs = client.calls[0]
    assert method == "patch"
    assert kwargs["params"] == {
        "id": "eq.p-1",
        "user_id": "eq.user-a",
        "select": "*",
    }
    assert kwargs["json"] == {"name": "Renamed", "status": "SCANNING"}
    assert project is not None
    assert project.name == "Renamed"
    assert project.status == ProjectStatus.SCANNING


def test_update_returns_none_when_not_found(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, []))

    project = asyncio.run(
        repo.update("user-a", "p-1", ProjectUpdate(name="Renamed"))
    )

    assert project is None


def test_update_with_empty_changes_falls_back_to_get(monkeypatch) -> None:
    """A no-op PATCH resolves to the current row rather than an empty PATCH."""
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    project = asyncio.run(repo.update("user-a", "p-1", ProjectUpdate()))

    assert project is not None
    assert project.id == "p-1"


def test_delete_returns_true_when_row_removed(monkeypatch) -> None:
    repo = _repo()
    _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    deleted = asyncio.run(repo.delete("user-a", "p-1"))

    assert deleted is True


def test_delete_returns_false_when_no_row_matched(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, []))

    deleted = asyncio.run(repo.delete("user-a", "p-1"))

    assert deleted is False
    params = client.calls[0][2]["params"]
    assert params["user_id"] == "eq.user-a"
    assert params["id"] == "eq.p-1"


def test_repository_requires_configuration_before_network(monkeypatch) -> None:
    repo = _repo(supabase_url="", supabase_service_role_key="")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("no network"))

    with pytest.raises(ProjectConfigurationError):
        asyncio.run(repo.create(ProjectCreate(user_id="user-a", name="X", website_url="https://x.com")))

    with pytest.raises(ProjectConfigurationError):
        asyncio.run(repo.list_by_user("user-a"))


def test_repository_maps_postgrest_errors(monkeypatch) -> None:
    repo = _repo()
    _patch_http(
        monkeypatch,
        FakeResponse(
            400,
            {"code": "PGRST200", "message": "Could not parse the request body", "details": "..."},
        ),
    )

    with pytest.raises(ProjectError) as excinfo:
        asyncio.run(repo.create(ProjectCreate(user_id="user-a", name="X", website_url="https://x.com")))

    assert "Could not parse the request body" in str(excinfo.value)
    assert "service-role-key" not in str(excinfo.value)
