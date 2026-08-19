"""Strategy generation API surface.

A single endpoint: generate candidate remediation strategies for one issue
or deterministic issue group of a completed scan owned by the authenticated
user. Ownership comes from the JWT (never from the body); missing or foreign
scans answer 404 (IDOR-safe), non-completed scans answer 409, and provider
problems answer 503/502 — all as the uniform ``{code, message}`` envelope.

This endpoint only generates candidates; evaluation/ranking is a later module.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.strategies import get_strategy_service
from app.schemas.strategies import StrategyGenerateRequest
from app.strategies.models import StrategyGeneration
from app.strategies.services import StrategyGenerationService

router = APIRouter(prefix="/scans", tags=["strategies"])

StrategyServiceDep = Annotated[StrategyGenerationService, Depends(get_strategy_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.post(
    "/{scan_id}/strategies",
    response_model=StrategyGeneration,
    summary="Generate candidate remediation strategies for an issue or group",
)
async def generate_scan_strategies(
    scan_id: UUID,
    payload: StrategyGenerateRequest,
    user: CurrentUserDep,
    service: StrategyServiceDep,
) -> StrategyGeneration:
    """Return 2–5 validated candidate strategies for the selected target."""
    return await service.generate_strategies(
        user.id,
        str(scan_id),
        issue_id=payload.issue_id,
        group_id=payload.group_id,
        strategy_count=payload.strategy_count,
    )
