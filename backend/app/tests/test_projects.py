"""Tests for the project management API.

Covers the full route → schema → service → repository stack using an
in-memory repository that faithfully implements the contract (queries scoped
to ``user_id``), so ownership/IDOR behavior is exercised end-to-end without
any network access.

Authentication is replaced via dependency overrides: ``get_current_user``
returns a fixed authenticated user, ``get_project_service`` a real service on
the in-memory repository.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.projects import get_project_service
from app.main import create_app
from app.projects.models import Project, ProjectCreate, ProjectStatus, ProjectUpdate
from app.projects.services import ProjectManagementService

USER_A = AuthUser(id="user-a", email="a@example.com", email_verified=True)
USER_B = AuthUser(id="user-b", email="b@example.com", email_verified=True)


class InMemoryProjectRepository:
    """Test double implementing :class:`ProjectRepository` semantics — every
    query is scoped to ``user_id`` exactly like the real PostgREST repository."""

    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}

    def seed(self, user_id: str, name: str = "Seed project", **overrides) -> Project:
        project = Project(
            id=str(uuid4()),
            user_id=user_id,
            name=name,
            description="",
            website_url="https://example.com",
            status=ProjectStatus.NOT_SCANNED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **overrides,
        )
        self._projects[project.id] = project
        return project

    async def create(self, data: ProjectCreate) -> Project:
        project = Project(
            id=str(uuid4()),
            user_id=data.user_id,
            name=data.name,
            description=data.description,
            website_url=data.website_url,
            status=data.status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._projects[project.id] = project
        return project

    async def list_by_user(self, user_id: str) -> List[Project]:
        owned = [p for p in self._projects.values() if p.user_id == user_id]
        return sorted(owned, key=lambda p: p.created_at, reverse=True)

    async def get(self, user_id: str, project_id: str) -> Optional[Project]:
        project = self._projects.get(project_id)
        if project is not None and project.user_id == user_id:
            return project
        return None

    async def update(
        self, user_id: str, project_id: str, changes: ProjectUpdate
    ) -> Optional[Project]:
        project = await self.get(user_id, project_id)
        if project is None:
            return None
        updates = changes.model_dump(exclude_none=True)
        self._projects[project_id] = project.model_copy(update=updates)
        return self._projects[project_id]

    async def delete(self, user_id: str, project_id: str) -> bool:
        project = self._projects.get(project_id)
        if project is None or project.user_id != user_id:
            return False
        del self._projects[project_id]
        return True


@pytest.fixture
def repo() -> InMemoryProjectRepository:
    return InMemoryProjectRepository()


def _client(repo: InMemoryProjectRepository, user: AuthUser = USER_A) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_project_service] = lambda: ProjectManagementService(repo)
    return TestClient(app)


# --- authentication & authorization ---------------------------------------


def test_project_endpoints_require_authentication(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)
    # Remove the auth override so the real bearer dependency runs.
    client.app.dependency_overrides[get_current_user] = get_current_user

    assert client.get("/api/v1/projects").status_code == 401
    pid = str(uuid4())
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post(
        "/api/v1/projects",
        json={"name": "My site", "website_url": "https://example.com"},
    ).status_code == 401
    assert client.patch(f"/api/v1/projects/{pid}", json={"name": "x"}).status_code == 401
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 401


def test_create_project(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)

    response = client.post(
        "/api/v1/projects",
        json={
            "name": "My accessibility project",
            "description": "Track our homepage",
            "website_url": "https://example.com",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My accessibility project"
    assert body["description"] == "Track our homepage"
    assert body["website_url"] == "https://example.com"
    assert body["status"] == "NOT_SCANNED"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]
    assert "user_id" not in body


def test_create_project_derives_ownership_from_authentication(
    repo: InMemoryProjectRepository,
) -> None:
    """A client-supplied ``user_id`` is ignored — ownership comes from the JWT."""
    client = _client(repo)

    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Sneaky",
            "website_url": "https://example.com",
            "user_id": "user-b",  # must be ignored
        },
    )

    assert response.status_code == 201
    # The created project is stored under the authenticated user.
    created = asyncio.run(repo.list_by_user("user-a"))
    assert len(created) == 1
    assert created[0].user_id == "user-a"


def test_create_project_normalizes_website_url(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)

    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Normalize",
            "website_url": "  HTTPS://Example.COM:443/foo#section  ",
        },
    )

    assert response.status_code == 201
    assert response.json()["website_url"] == "https://example.com/foo"


def test_create_project_rejects_invalid_url(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)
    for bad in (
        "not-a-url",
        "ftp://example.com",
        "https://",
        "https://exa mple.com",
        "http://example.com:99999",
    ):
        response = client.post(
            "/api/v1/projects", json={"name": "Bad", "website_url": bad}
        )
        assert response.status_code == 422, f"expected 422 for {bad!r}"


def test_create_project_rejects_invalid_name(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)
    for bad_name in ("", "   ", "x" * 101):
        response = client.post(
            "/api/v1/projects",
            json={"name": bad_name, "website_url": "https://example.com"},
        )
        assert response.status_code == 422, f"expected 422 for name {bad_name!r}"


def test_create_project_rejects_long_description(repo: InMemoryProjectRepository) -> None:
    client = _client(repo)
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Too long",
            "website_url": "https://example.com",
            "description": "x" * 2001,
        },
    )
    assert response.status_code == 422


# --- list -----------------------------------------------------------------


def test_list_projects_returns_only_own(repo: InMemoryProjectRepository) -> None:
    repo.seed("user-a", name="A-one")
    repo.seed("user-a", name="A-two")
    repo.seed("user-b", name="B-one")

    client = _client(repo)
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert set(names) == {"A-one", "A-two"}


# --- get ------------------------------------------------------------------


def test_get_own_project(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-a", name="Mine")

    response = _client(repo).get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Mine"


def test_get_another_users_project_returns_404(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-b", name="Theirs")

    response = _client(repo).get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 404
    assert response.json() == {"code": "project_not_found", "message": "Project not found."}


def test_get_missing_project_returns_404(repo: InMemoryProjectRepository) -> None:
    response = _client(repo).get(f"/api/v1/projects/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"


def test_get_project_rejects_malformed_id(repo: InMemoryProjectRepository) -> None:
    response = _client(repo).get("/api/v1/projects/not-a-uuid")
    assert response.status_code == 422


# --- update ----------------------------------------------------------------


def test_update_own_project(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-a", name="Old")

    response = _client(repo).patch(
        f"/api/v1/projects/{project.id}",
        json={"name": "New", "description": "updated"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New"
    assert body["description"] == "updated"
    assert body["website_url"] == "https://example.com"


def test_update_project_status_validates(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-a")
    client = _client(repo)

    ok = client.patch(f"/api/v1/projects/{project.id}", json={"status": "SCANNING"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "SCANNING"

    bad = client.patch(f"/api/v1/projects/{project.id}", json={"status": "DONE"})
    assert bad.status_code == 422


def test_update_requires_at_least_one_field(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-a")
    response = _client(repo).patch(f"/api/v1/projects/{project.id}", json={})
    assert response.status_code == 422


def test_update_another_users_project_returns_404(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-b")

    response = _client(repo).patch(
        f"/api/v1/projects/{project.id}", json={"name": "Hijack"}
    )

    assert response.status_code == 404
    stored = asyncio.run(repo.get("user-b", project.id))
    assert stored is not None
    assert stored.name == "Seed project"


# --- delete ----------------------------------------------------------------


def test_delete_own_project(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-a")

    response = _client(repo).delete(f"/api/v1/projects/{project.id}")

    assert response.status_code == 204
    assert asyncio.run(repo.get("user-a", project.id)) is None


def test_delete_another_users_project_returns_404(repo: InMemoryProjectRepository) -> None:
    project = repo.seed("user-b")

    response = _client(repo).delete(f"/api/v1/projects/{project.id}")

    assert response.status_code == 404
    assert asyncio.run(repo.get("user-b", project.id)) is not None


def test_delete_missing_project_returns_404(repo: InMemoryProjectRepository) -> None:
    response = _client(repo).delete(f"/api/v1/projects/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "project_not_found"


# --- service-level ownership (direct unit tests) --------------------------


def test_service_scopes_every_operation_to_the_user(repo: InMemoryProjectRepository) -> None:
    """The service forwards the authenticated user id on every call and the
    repository refuses cross-user access — the two layers together prevent
    IDOR even if one of them regresses."""
    service = ProjectManagementService(repo)
    theirs = repo.seed("user-b", name="Theirs")

    async def check() -> None:
        with pytest.raises(Exception) as excinfo:
            await service.get_for_user("user-a", theirs.id)
        assert excinfo.value.status_code == 404

        with pytest.raises(Exception) as excinfo:
            await service.update_for_user(
                "user-a", theirs.id, ProjectUpdate(name="Hijack")
            )
        assert excinfo.value.status_code == 404

        with pytest.raises(Exception) as excinfo:
            await service.delete_for_user("user-a", theirs.id)
        assert excinfo.value.status_code == 404

    asyncio.run(check())

    # And user B's project is untouched.
    assert asyncio.run(repo.get("user-b", theirs.id)) is not None
