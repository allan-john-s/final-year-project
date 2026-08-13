"""Project dependencies for route handlers.

- :func:`get_project_repository` — the persistence seam (currently Supabase
  PostgREST; swappable in tests).
- :func:`get_project_service` — the service built on that repository.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.projects.interfaces import ProjectRepository
from app.projects.services import ProjectManagementService
from app.repositories.projects import SupabaseProjectRepository


def get_project_repository() -> ProjectRepository:
    """Resolve the configured project repository (DI seam)."""
    return SupabaseProjectRepository(get_settings())


def get_project_service(
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ProjectManagementService:
    """Resolve the project management service."""
    return ProjectManagementService(repository)
