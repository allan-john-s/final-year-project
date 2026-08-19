"""Scan dependencies for route handlers.

- :func:`get_scan_repository` — the persistence seam for scans (currently
  Supabase PostgREST; swappable in tests).
- :func:`get_issue_repository` — the persistence seam for accessibility
  issues.
- :func:`get_scan_service` — the execution service built on the repositories
  (plus the project repository for ownership verification).
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.dependencies.projects import get_project_repository
from app.repositories.issues import SupabaseAccessibilityIssueRepository
from app.repositories.scans import SupabaseScanRepository
from app.scans.interfaces import AccessibilityIssueRepository, ScanRepository
from app.scans.services import ScanExecutionService
from app.projects.interfaces import ProjectRepository


def get_scan_repository() -> ScanRepository:
    """Resolve the configured scan repository (DI seam)."""
    return SupabaseScanRepository(get_settings())


def get_issue_repository() -> AccessibilityIssueRepository:
    """Resolve the configured accessibility issue repository (DI seam)."""
    return SupabaseAccessibilityIssueRepository(get_settings())


def get_scan_service(
    scans: Annotated[ScanRepository, Depends(get_scan_repository)],
    issues: Annotated[AccessibilityIssueRepository, Depends(get_issue_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ScanExecutionService:
    """Resolve the scan execution service."""
    return ScanExecutionService(scans=scans, issues=issues, projects=projects)
