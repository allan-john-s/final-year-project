"""Scan API surface.

Every endpoint requires authentication (bearer dependency) and derives
ownership from the authenticated user's id — the request body can never set
``user_id`` (or ``project_id``, which lives in the path). Routes stay thin:
schema validation → service → repositories. ``POST .../scan`` schedules the
real execution as a FastAPI background task and returns the RUNNING scan
immediately; clients poll ``GET /scans/{id}`` until COMPLETED/FAILED.

The API never instantiates a scanner engine — it asks the service, which
selects one through the factory registry (Axe today, Lighthouse later,
without any API change).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.scans import get_scan_service
from app.schemas.issues import IssueResponse
from app.schemas.scans import ScanResponse, ScanStartRequest
from app.scans.services import ScanExecutionService

router = APIRouter(prefix="/scans", tags=["scans"])
project_router = APIRouter(prefix="/projects", tags=["scans"])

ScanServiceDep = Annotated[ScanExecutionService, Depends(get_scan_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@project_router.post(
    "/{project_id}/scan",
    response_model=ScanResponse,
    status_code=202,
    summary="Start a scan for a project",
)
async def start_project_scan(
    project_id: UUID,
    payload: ScanStartRequest,
    user: CurrentUserDep,
    service: ScanServiceDep,
    background_tasks: BackgroundTasks,
) -> ScanResponse:
    """Validate ownership, create the scan (PENDING → RUNNING), then execute
    the scanner in the background. Returns the RUNNING scan."""
    scan = await service.start_scan(user.id, str(project_id), payload.scanner_type)
    background_tasks.add_task(service.run_scan, user.id, scan.id)
    return ScanResponse(**scan.model_dump())


@project_router.get(
    "/{project_id}/scans",
    response_model=list[ScanResponse],
    summary="List a project's scans",
)
async def list_project_scans(
    project_id: UUID,
    user: CurrentUserDep,
    service: ScanServiceDep,
) -> list[ScanResponse]:
    scans = await service.list_for_project(user.id, str(project_id))
    return [ScanResponse(**scan.model_dump()) for scan in scans]


@router.get("", response_model=list[ScanResponse], summary="List my scans")
async def list_scans(
    user: CurrentUserDep,
    service: ScanServiceDep,
) -> list[ScanResponse]:
    scans = await service.list_for_user(user.id)
    return [ScanResponse(**scan.model_dump()) for scan in scans]


@router.get(
    "/{scan_id}",
    response_model=ScanResponse,
    summary="Get a scan",
)
async def get_scan(
    scan_id: UUID,
    user: CurrentUserDep,
    service: ScanServiceDep,
) -> ScanResponse:
    scan = await service.get_for_user(user.id, str(scan_id))
    return ScanResponse(**scan.model_dump())


@router.get(
    "/{scan_id}/issues",
    response_model=list[IssueResponse],
    summary="List a scan's accessibility issues",
)
async def get_scan_issues(
    scan_id: UUID,
    user: CurrentUserDep,
    service: ScanServiceDep,
) -> list[IssueResponse]:
    issues = await service.get_issues_for_user(user.id, str(scan_id))
    return [IssueResponse(**issue.model_dump()) for issue in issues]


@router.delete(
    "/{scan_id}",
    status_code=204,
    summary="Delete a scan",
)
async def delete_scan(
    scan_id: UUID,
    user: CurrentUserDep,
    service: ScanServiceDep,
) -> None:
    await service.delete_for_user(user.id, str(scan_id))
