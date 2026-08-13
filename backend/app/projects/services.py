"""Project management service.

Owns the business rules: ownership is always derived from the authenticated
user id passed in by the route (never from the request body), and every
read/write goes through the repository scoped to that user. Missing or
not-owned projects surface as the same :class:`ProjectNotFoundError` (404) so
responses never reveal whether another user's project exists.
"""

from app.projects.exceptions import ProjectNotFoundError
from app.projects.interfaces import ProjectRepository
from app.projects.models import Project, ProjectCreate, ProjectCreateInput, ProjectUpdate


class ProjectManagementService:
    """CRUD orchestration for projects, enforced per authenticated user."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    async def create(self, user_id: str, payload: ProjectCreateInput) -> Project:
        """Create a project owned by ``user_id``."""
        return await self._repository.create(
            ProjectCreate(user_id=user_id, **payload.model_dump())
        )

    async def list_for_user(self, user_id: str) -> list[Project]:
        """Return every project owned by ``user_id``, newest first."""
        return await self._repository.list_by_user(user_id)

    async def get_for_user(self, user_id: str, project_id: str) -> Project:
        """Return ``project_id`` if owned by ``user_id``, else 404."""
        project = await self._repository.get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError("Project not found.")
        return project

    async def update_for_user(
        self,
        user_id: str,
        project_id: str,
        changes: ProjectUpdate,
    ) -> Project:
        """Apply partial ``changes`` to an owned project, else 404."""
        project = await self._repository.update(user_id, project_id, changes)
        if project is None:
            raise ProjectNotFoundError("Project not found.")
        return project

    async def delete_for_user(self, user_id: str, project_id: str) -> None:
        """Delete an owned project, else 404."""
        deleted = await self._repository.delete(user_id, project_id)
        if not deleted:
            raise ProjectNotFoundError("Project not found.")
