"""Measurement dependencies for route handlers (Module 8).

- :func:`get_measurement_service` — the measurement service built on the
  scan execution service, remediation store, and measurement store.
"""

from typing import Annotated

from fastapi import Depends

from app.dependencies.projects import get_project_repository
from app.dependencies.scans import get_issue_repository, get_scan_repository
from app.measurements.interfaces import ScanAccessor
from app.measurements.services import MeasurementService
from app.measurements.store import InMemoryMeasurementStore, get_measurement_store
from app.projects.interfaces import ProjectRepository
from app.remediations.store import RemediationStore, get_remediation_store
from app.scans.interfaces import AccessibilityIssueRepository, ScanRepository
from app.scans.services import ScanExecutionService


class ScanAccessorAdapter(ScanAccessor):
    """Adapts the existing ScanExecutionService to the ScanAccessor interface."""

    def __init__(self, scan_service: ScanExecutionService) -> None:
        self._scan_service = scan_service

    async def get_scan(self, user_id: str, scan_id: str):
        """Retrieve a scan via the existing scan execution service."""
        return await self._scan_service.get_for_user(user_id, scan_id)


def get_scan_service(
    scans: Annotated[ScanRepository, Depends(get_scan_repository)],
    issues: Annotated[AccessibilityIssueRepository, Depends(get_issue_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ScanExecutionService:
    """Resolve the scan execution service."""
    return ScanExecutionService(scans=scans, issues=issues, projects=projects)


def get_scan_accessor(
    scan_service: Annotated[ScanExecutionService, Depends(get_scan_service)],
) -> ScanAccessorAdapter:
    """Resolve the scan accessor."""
    return ScanAccessorAdapter(scan_service)


def get_measurement_service(
    scan_accessor: Annotated[ScanAccessorAdapter, Depends(get_scan_accessor)],
    remediation_store: Annotated[RemediationStore, Depends(get_remediation_store)],
    measurement_store: Annotated[InMemoryMeasurementStore, Depends(get_measurement_store)],
) -> MeasurementService:
    """Resolve the measurement service."""
    return MeasurementService(
        scan_accessor=scan_accessor,
        remediation_store=remediation_store,
        measurement_store=measurement_store,
    )
