"""Context dependencies for route handlers.

:func:`get_context_service` — the :class:`ContextBuilderService` built on the
same repository seams as the scan service (swappable in tests).
"""

from typing import Annotated

from fastapi import Depends

from app.context.services import ContextBuilderService
from app.dependencies.projects import get_project_repository
from app.dependencies.scans import get_issue_repository, get_scan_repository
from app.projects.interfaces import ProjectRepository
from app.scans.interfaces import AccessibilityIssueRepository, ScanRepository


def get_context_service(
    scans: Annotated[ScanRepository, Depends(get_scan_repository)],
    issues: Annotated[AccessibilityIssueRepository, Depends(get_issue_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ContextBuilderService:
    """Resolve the context builder service."""
    return ContextBuilderService(scans=scans, issues=issues, projects=projects)
