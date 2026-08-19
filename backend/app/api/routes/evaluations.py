"""Strategy evaluation API surface.

A single endpoint: evaluate one or more supplied candidate strategies for an
issue or deterministic issue group of a completed scan owned by the
authenticated user. Ownership comes from the JWT (never from the body);
missing or foreign scans answer 404 (IDOR-safe), non-completed scans answer
409, unknown targets answer 404, strategies that do not match the target
answer 422, and provider problems answer 503/502 — all as the uniform
``{code, message}`` envelope.

This endpoint only produces per-candidate multidimensional evaluations;
ranking/winner selection is a later module.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.evaluations import get_evaluation_service
from app.evaluations.models import EvaluationBatch
from app.evaluations.services import StrategyEvaluationService
from app.schemas.evaluations import StrategyEvaluateRequest

router = APIRouter(prefix="/scans", tags=["evaluations"])

EvaluationServiceDep = Annotated[StrategyEvaluationService, Depends(get_evaluation_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.post(
    "/{scan_id}/evaluations",
    response_model=EvaluationBatch,
    summary="Evaluate candidate remediation strategies for an issue or group",
)
async def evaluate_scan_strategies(
    scan_id: UUID,
    payload: StrategyEvaluateRequest,
    user: CurrentUserDep,
    service: EvaluationServiceDep,
) -> EvaluationBatch:
    """Return one independent 7-dimensional evaluation per supplied strategy."""
    return await service.evaluate_strategies(
        user.id,
        str(scan_id),
        issue_id=payload.issue_id,
        group_id=payload.group_id,
        strategies=payload.strategies,
    )
