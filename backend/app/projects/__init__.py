"""Project management domain.

Module 2 adds the first real persistence-backed feature: projects owned by an
authenticated user. The layer order is route → schema → service → repository →
Supabase (PostgREST). Ownership is derived from the authenticated JWT identity
and enforced both here (service) and in the repository queries.
"""

from app.projects.exceptions import (
    ProjectConfigurationError,
    ProjectError,
    ProjectNotFoundError,
)
from app.projects.interfaces import ProjectRepository
from app.projects.models import (
    Project,
    ProjectCreate,
    ProjectCreateInput,
    ProjectStatus,
    ProjectUpdate,
)
from app.projects.services import ProjectManagementService

__all__ = [
    "Project",
    "ProjectConfigurationError",
    "ProjectCreate",
    "ProjectCreateInput",
    "ProjectError",
    "ProjectManagementService",
    "ProjectNotFoundError",
    "ProjectRepository",
    "ProjectStatus",
    "ProjectUpdate",
]
