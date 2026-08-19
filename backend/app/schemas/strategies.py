"""API schemas for strategy generation.

The request never accepts ``user_id`` (identity comes from the JWT) and
never references projects — the scan id in the path determines ownership.
"""

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class StrategyGenerateRequest(BaseModel):
    """Body for ``POST /api/v1/scans/{scan_id}/strategies``.

    Exactly one of ``issue_id`` / ``group_id`` is required (both may be given
    only when the issue belongs to the group).
    """

    issue_id: Optional[str] = Field(default=None, max_length=64)
    group_id: Optional[str] = Field(default=None, max_length=128)
    strategy_count: int = Field(default=3, ge=2, le=5)

    @model_validator(mode="after")
    def _require_target(self) -> "StrategyGenerateRequest":
        if not self.issue_id and not self.group_id:
            raise ValueError(
                "Provide either issue_id or group_id to generate strategies for."
            )
        return self
