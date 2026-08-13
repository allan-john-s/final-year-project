"""Project repository contract.

The persistence boundary — the only place that talks to storage. Services and
routes depend on this protocol, never on a concrete implementation, so tests
can inject an in-memory fake and future storage backends slot in unchanged.

Every method takes the owning ``user_id`` explicitly; implementations MUST
scope their queries to that user so ownership is enforced at the data layer
(not just in route code).
"""

from typing import Optional, Protocol

from app.projects.models import Project, ProjectCreate, ProjectUpdate


class ProjectRepository(Protocol):
    """Data access for projects, always scoped to a single user."""

    async def create(self, data: ProjectCreate) -> Project:
        """Persist a new project and return it."""
        ...

    async def list_by_user(self, user_id: str) -> list[Project]:
        """Return the projects owned by ``user_id``, newest first."""
        ...

    async def get(self, user_id: str, project_id: str) -> Optional[Project]:
        """Return ``project_id`` if owned by ``user_id``, else ``None``."""
        ...

    async def update(
        self,
        user_id: str,
        project_id: str,
        changes: ProjectUpdate,
    ) -> Optional[Project]:
        """Apply ``changes`` to ``project_id`` if owned; return it or ``None``."""
        ...

    async def delete(self, user_id: str, project_id: str) -> bool:
        """Delete ``project_id`` if owned; return whether a row was removed."""
        ...
