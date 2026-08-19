"""API schemas for remediation proposals (Module 7).

The request identifies the scan, issue, and strategy to remediate. The
server validates ownership and ensures the strategy is the recommended one.

The request never accepts ``user_id`` (identity comes from the JWT).
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.evaluations.models import StrategyEvaluation
from app.remediations.models import RemediationStatus
from app.strategies.models import CandidateStrategy


class RemediationCreateRequest(BaseModel):
    """Body for ``POST /api/v1/scans/{scan_id}/remediation``.

    Identifies the issue and strategy to remediate. The service validates
    that the strategy is the recommended (top-ranked) one.
    """

    issue_id: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=64)
    strategies: List[CandidateStrategy] = Field(min_length=1, max_length=10)
    evaluations: List[StrategyEvaluation] = Field(min_length=1, max_length=10)


class RemediationStatusUpdateRequest(BaseModel):
    """Body for ``PATCH /api/v1/remediations/{remediation_id}/status``."""

    status: RemediationStatus
