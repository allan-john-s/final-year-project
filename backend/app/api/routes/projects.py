"""Project management API surface.

Every endpoint requires authentication (bearer dependency) and derives
ownership from the authenticated user's id — the request body can never set
``user_id``. Routes stay thin: schema validation → service → repository.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.projects import get_project_service
from app.projects.models import ProjectCreateInput, ProjectUpdate
from app.projects.services import ProjectManagementService
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectServiceDep = Annotated[ProjectManagementService, Depends(get_project_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=201,
    summary="Create a project",
)
async def create_project(
    payload: ProjectCreateRequest,
    user: CurrentUserDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    project = await service.create(
        user.id,
        ProjectCreateInput(**payload.model_dump()),
    )
    return ProjectResponse(**project.model_dump())


@router.get("", response_model=list[ProjectResponse], summary="List my projects")
async def list_projects(
    user: CurrentUserDep,
    service: ProjectServiceDep,
) -> list[ProjectResponse]:
    projects = await service.list_for_user(user.id)
    return [ProjectResponse(**project.model_dump()) for project in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project",
)
async def get_project(
    project_id: UUID,
    user: CurrentUserDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    project = await service.get_for_user(user.id, str(project_id))
    return ProjectResponse(**project.model_dump())


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdateRequest,
    user: CurrentUserDep,
    service: ProjectServiceDep,
) -> ProjectResponse:
    project = await service.update_for_user(
        user.id,
        str(project_id),
        ProjectUpdate(**payload.model_dump()),
    )
    return ProjectResponse(**project.model_dump())


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete a project",
)
async def delete_project(
    project_id: UUID,
    user: CurrentUserDep,
    service: ProjectServiceDep,
) -> None:
    await service.delete_for_user(user.id, str(project_id))
