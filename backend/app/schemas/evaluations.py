"""API schemas for strategy evaluation.

Strategies are generated on demand and never persisted (Module 4), so the
evaluation request carries the full candidate strategies alongside their ids.
The backend re-validates every strategy against the deterministic
ContextDocument — client-supplied ids are never trusted on their own.

The request never accepts ``user_id`` (identity comes from the JWT).
"""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.strategies.models import CandidateStrategy


class StrategyEvaluateRequest(BaseModel):
    """Body for ``POST /api/v1/scans/{scan_id}/evaluations``.

    Exactly one of ``issue_id`` / ``group_id`` is required (both may be given
    only when the issue belongs to the group). ``strategy_ids`` must match
    the ids of the supplied ``strategies`` exactly.
    """

    issue_id: Optional[str] = Field(default=None, max_length=64)
    group_id: Optional[str] = Field(default=None, max_length=128)
    strategy_ids: List[str] = Field(min_length=1, max_length=10)
    strategies: List[CandidateStrategy] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _require_target(self) -> "StrategyEvaluateRequest":
        if not self.issue_id and not self.group_id:
            raise ValueError(
                "Provide either issue_id or group_id to evaluate strategies for."
            )
        return self

    @model_validator(mode="after")
    def _ids_match_strategies(self) -> "StrategyEvaluateRequest":
        supplied = {item.strip() for item in self.strategy_ids if item.strip()}
        actual = {strategy.strategy_id for strategy in self.strategies}
        if supplied != actual:
            raise ValueError(
                "strategy_ids must match the ids of the supplied strategies."
            )
        return self
