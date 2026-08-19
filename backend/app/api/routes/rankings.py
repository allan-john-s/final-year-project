"""Strategy ranking API surface (Module 6).

A single endpoint: rank supplied evaluated candidate strategies for an
issue or deterministic issue group of a completed scan owned by the
authenticated user. Ownership comes from the JWT (never from the body);
missing or foreign scans answer 404 (IDOR-safe), non-completed scans
answer 409, unknown targets answer 404, and invalid configuration
answers 422 — all as the uniform ``{code, message}`` envelope.

Ranking is fully deterministic and does not call an LLM. The endpoint
produces a transparent, explainable ranking of strategies.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.rankings import get_ranking_service
from app.rankings.models import RankingBatch
from app.rankings.services import StrategyRankingService
from app.schemas.rankings import StrategyRankRequest

router = APIRouter(prefix="/scans", tags=["rankings"])

RankingServiceDep = Annotated[StrategyRankingService, Depends(get_ranking_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]


@router.post(
    "/{scan_id}/ranking",
    response_model=RankingBatch,
    summary="Rank candidate remediation strategies for an issue or group",
)
async def rank_scan_strategies(
    scan_id: UUID,
    payload: StrategyRankRequest,
    user: CurrentUserDep,
    service: RankingServiceDep,
) -> RankingBatch:
    """Return a ranked list of strategies with weighted scores and explanations."""
    return await service.rank_strategies(
        user.id,
        str(scan_id),
        issue_id=payload.issue_id,
        group_id=payload.group_id,
        strategies=payload.strategies,
        evaluations=payload.evaluations,
        mode=payload.mode,
    )
