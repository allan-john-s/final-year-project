"""Remediation API surface (Module 7).

Endpoints for generating, retrieving, and managing remediation proposals
for ranked accessibility strategies.

- POST /api/v1/scans/{scan_id}/remediation — generate a proposal
- GET /api/v1/scans/{scan_id}/remediations — list proposals for a scan
- GET /api/v1/remediations/{remediation_id} — get a specific proposal
- PATCH /api/v1/remediations/{remediation_id}/status — update status

All endpoints require authentication. Ownership is validated through
the context builder (scan must belong to the authenticated user).
"""

from typing import Annotated, List

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.remediations import get_remediation_service
from app.remediations.exceptions import (
    RemediationInvalidTransitionError,
    RemediationNotFoundError,
)
from app.remediations.models import RemediationProposal
from app.remediations.services import RemediationService
from app.remediations.store import RemediationStore, get_remediation_store
from app.schemas.remediations import (
    RemediationCreateRequest,
    RemediationStatusUpdateRequest,
)

router = APIRouter(prefix="/scans", tags=["remediations"])
remediation_router = APIRouter(prefix="/remediations", tags=["remediations"])

RemediationServiceDep = Annotated[RemediationService, Depends(get_remediation_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
StoreDep = Annotated[RemediationStore, Depends(get_remediation_store)]


@router.post(
    "/{scan_id}/remediation",
    response_model=RemediationProposal,
    summary="Generate a remediation proposal for the recommended strategy",
)
async def generate_remediation(
    scan_id: str,
    payload: RemediationCreateRequest,
    user: CurrentUserDep,
    service: RemediationServiceDep,
    store: StoreDep,
) -> RemediationProposal:
    """Generate a remediation proposal for the top-ranked strategy.

    The server validates that:
    - The scan belongs to the authenticated user
    - The issue belongs to the scan
    - The strategy belongs to the issue
    - The strategy was evaluated
    - The strategy is the recommended (rank #1) strategy
    """
    proposal = await service.generate_proposal(
        user.id,
        scan_id,
        issue_id=payload.issue_id,
        strategy_id=payload.strategy_id,
        strategies=payload.strategies,
        evaluations=payload.evaluations,
    )
    store.save(proposal)
    return proposal


@router.get(
    "/{scan_id}/remediations",
    response_model=List[RemediationProposal],
    summary="List remediation proposals for a scan",
)
async def list_remediations(
    scan_id: str,
    user: CurrentUserDep,
    store: StoreDep,
) -> List[RemediationProposal]:
    """List all remediation proposals for a scan."""
    return store.list_for_scan(scan_id, user.id)


@remediation_router.get(
    "/{remediation_id}",
    response_model=RemediationProposal,
    summary="Get a specific remediation proposal",
)
async def get_remediation(
    remediation_id: str,
    user: CurrentUserDep,
    store: StoreDep,
) -> RemediationProposal:
    """Get a remediation proposal by ID."""
    proposal = store.get(remediation_id)
    if proposal is None:
        raise RemediationNotFoundError("The remediation proposal was not found.")
    return proposal


@remediation_router.patch(
    "/{remediation_id}/status",
    response_model=RemediationProposal,
    summary="Update a remediation proposal's status",
)
async def update_remediation_status(
    remediation_id: str,
    payload: RemediationStatusUpdateRequest,
    user: CurrentUserDep,
    store: StoreDep,
) -> RemediationProposal:
    """Update a proposal's status with valid transitions only."""
    proposal = store.get(remediation_id)
    if proposal is None:
        raise RemediationNotFoundError("The remediation proposal was not found.")

    # Validate the transition.
    RemediationService.validate_status_transition(proposal.status, payload.status)

    return store.update_status(remediation_id, payload.status)
