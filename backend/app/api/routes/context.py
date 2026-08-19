"""Context API surface.

A single read-only endpoint: build the structured :class:`ContextDocument`
for a completed scan owned by the authenticated user. Ownership is derived
from the JWT (never the URL/body beyond ``scan_id``); missing or foreign
scans answer the same 404 (IDOR-safe), non-completed scans answer 409.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.context.models import ContextDocument
from app.dependencies.auth import get_current_user
from app.dependencies.context import get_context_service
from app.context.services import ContextBuilderService

router = APIRouter(prefix="/scans", tags=["context"])

ContextServiceDep = Annotated[ContextBuilderService, Depends(get_context_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.get(
    "/{scan_id}/context",
    response_model=ContextDocument,
    summary="Build the context document for a completed scan",
)
async def get_scan_context(
    scan_id: UUID,
    user: CurrentUserDep,
    service: ContextServiceDep,
) -> ContextDocument:
    """Return deterministic, versioned context for an owned completed scan."""
    return await service.build_for_scan(user.id, str(scan_id))
