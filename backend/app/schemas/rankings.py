"""API schemas for strategy ranking (Module 6).

The request identifies the target (issue or group), the ranking mode, and
carries the full candidate strategies plus their evaluations. The backend
re-validates every strategy and evaluation against the deterministic
ContextDocument — client-supplied ids are never trusted on their own.

The request never accepts ``user_id`` (identity comes from the JWT).
"""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.evaluations.models import StrategyEvaluation
from app.rankings.models import RankingMode
from app.strategies.models import CandidateStrategy


class StrategyRankRequest(BaseModel):
    """Body for ``POST /api/v1/scans/{scan_id}/ranking``.

    Exactly one of ``issue_id`` / ``group_id`` is required (both may be
    given only when the issue belongs to the group). ``strategy_ids``
    must match the ids of the supplied ``strategies`` exactly, and
    ``evaluations`` must contain an evaluation for each strategy.
    """

    issue_id: Optional[str] = Field(default=None, max_length=64)
    group_id: Optional[str] = Field(default=None, max_length=128)
    strategy_ids: List[str] = Field(min_length=2, max_length=10)
    strategies: List[CandidateStrategy] = Field(min_length=2, max_length=10)
    evaluations: List[StrategyEvaluation] = Field(min_length=1, max_length=10)
    mode: RankingMode = RankingMode.CONTEXTUAL

    @model_validator(mode="after")
    def _require_target(self) -> "StrategyRankRequest":
        if not self.issue_id and not self.group_id:
            raise ValueError(
                "Provide either issue_id or group_id to rank strategies for."
            )
        return self

    @model_validator(mode="after")
    def _ids_match_strategies(self) -> "StrategyRankRequest":
        supplied = {item.strip() for item in self.strategy_ids if item.strip()}
        actual = {strategy.strategy_id for strategy in self.strategies}
        if supplied != actual:
            raise ValueError(
                "strategy_ids must match the ids of the supplied strategies."
            )
        return self

    @model_validator(mode="after")
    def _evaluations_match_strategies(self) -> "StrategyRankRequest":
        strategy_ids = {s.strategy_id for s in self.strategies}
        eval_ids = {e.strategy_id for e in self.evaluations}
        if not eval_ids.issubset(strategy_ids):
            raise ValueError(
                "Evaluations must correspond to the supplied strategies."
            )
        return self
