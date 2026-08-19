"""Strategy ranking domain models (Module 6).

A :class:`RankedStrategy` is the result of combining a candidate strategy
(Module 4) with its seven-dimensional evaluation (Module 5) through a
transparent weighted scoring algorithm.

Research separation (deliberate):

- Module 4 *generates* multiple alternatives (:class:`CandidateStrategy`).
- Module 5 *evaluates* every alternative independently across seven
  bounded 0–10 dimensions (:class:`StrategyEvaluation`).
- Module 6 *ranks* those evaluated strategies using configurable,
  context-aware weights — no LLM, fully deterministic.

Score semantics (from Module 5 — all higher-is-better):

- accessibility_impact_score: 10 = excellent accessibility improvement
- standards_compliance_score: 10 = excellent WCAG compliance
- contextual_suitability_score: 10 = excellent fit for this specific context
- implementation_effort_score: 10 = very easy / very low effort
- maintainability_score: 10 = excellent long-term maintainability
- compatibility_score: 10 = excellent browser/AT compatibility
- risk_score: 10 = very low risk of negative side effects

All seven dimensions share the same direction (higher = better), so the
weighted sum requires no inversions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

RANKING_VERSION = "1.0"
"""The current ranking representation version."""

# The seven evaluation dimensions used for ranking, in canonical order.
# These MUST match app.evaluations.models.EVALUATION_CRITERIA.
RANKING_DIMENSIONS = [
    "accessibility_impact",
    "standards_compliance",
    "contextual_suitability",
    "implementation_effort",
    "maintainability",
    "compatibility",
    "risk",
]
"""The seven dimensions used for weighted ranking."""


class RankingMode(str, Enum):
    """Ranking mode — controls how weights are determined.

    BASELINE uses fixed default weights; CONTEXTUAL adjusts weights
    according to the ContextDocument for the specific accessibility issue.
    """

    BASELINE = "baseline"
    CONTEXTUAL = "contextual"


class RankingWeights(BaseModel):
    """Typed weight configuration for the seven ranking dimensions.

    Weights must sum to 1.0 (±tolerance) and every weight must be ≥ 0.
    """

    accessibility_impact: float = Field(ge=0.0, le=1.0)
    standards_compliance: float = Field(ge=0.0, le=1.0)
    contextual_suitability: float = Field(ge=0.0, le=1.0)
    implementation_effort: float = Field(ge=0.0, le=1.0)
    maintainability: float = Field(ge=0.0, le=1.0)
    compatibility: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)

    @field_validator("accessibility_impact", "standards_compliance", "contextual_suitability",
                     "implementation_effort", "maintainability", "compatibility", "risk",
                     mode="before")
    @classmethod
    def _round_weight(cls, value: object) -> object:
        """Round to 4 decimal places to avoid floating-point drift."""
        if isinstance(value, (int, float)):
            return round(float(value), 4)
        return value

    def total(self) -> float:
        """Return the sum of all weights (should be ≈ 1.0)."""
        return round(
            self.accessibility_impact
            + self.standards_compliance
            + self.contextual_suitability
            + self.implementation_effort
            + self.maintainability
            + self.compatibility
            + self.risk,
            6,
        )

    def to_dict(self) -> dict:
        """Return weights as a plain dict for traceability."""
        return {
            "accessibility_impact": self.accessibility_impact,
            "standards_compliance": self.standards_compliance,
            "contextual_suitability": self.contextual_suitability,
            "implementation_effort": self.implementation_effort,
            "maintainability": self.maintainability,
            "compatibility": self.compatibility,
            "risk": self.risk,
        }


class ContextFactor(BaseModel):
    """A detected contextual factor that influences ranking weights.

    Factors are derived deterministically from the ContextDocument —
    never invented, never produced by an LLM.
    """

    factor: str = Field(min_length=1, max_length=64)
    detected: bool
    influence: float = Field(ge=-1.0, le=1.0)
    affected_dimensions: List[str] = Field(min_length=1, max_length=7)
    explanation: str = Field(min_length=1, max_length=500)


class RankedStrategy(BaseModel):
    """One ranked strategy with its weighted score and explanation.

    Contains the strategy id, its rank position, the weighted score used
    for ordering, the individual dimension scores, and a human-readable
    explanation of why it received its ranking.
    """

    strategy_id: str = Field(min_length=1, max_length=64)
    rank: int = Field(ge=1, le=10)
    weighted_score: float = Field(ge=0.0, le=10.0)
    dimension_scores: dict = Field(default_factory=dict)
    strengths: List[str] = Field(default_factory=list, max_length=10)
    weaknesses: List[str] = Field(default_factory=list, max_length=10)
    ranking_explanation: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)


class RankingResult(BaseModel):
    """The complete ranking result: traceability + ranked strategies + context.

    Returned by the API for a single ranking request. Contains the ranked
    list of strategies, the weights used, the contextual factors detected,
    and metadata for research traceability.
    """

    scan_id: str
    issue_id: Optional[str] = None
    group_id: Optional[str] = None
    context_version: str
    ranking_version: str = RANKING_VERSION
    ranking_method: str  # "baseline" | "contextual"
    weights_used: RankingWeights
    context_factors: List[ContextFactor] = Field(default_factory=list)
    ranked_strategies: List[RankedStrategy] = Field(min_length=1, max_length=10)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RankingBatch(BaseModel):
    """API response: ranking metadata plus the ranked strategies.

    Provides traceability (scan/target/versions/weights) and the ranked
    list. No total score beyond weighted_score; no ranking beyond
    rank position.
    """

    scan_id: str
    issue_id: Optional[str] = None
    group_id: Optional[str] = None
    context_version: str
    ranking_version: str = RANKING_VERSION
    ranking_method: str
    weights_used: RankingWeights
    context_factors: List[ContextFactor] = Field(default_factory=list)
    ranked_strategies: List[RankedStrategy] = Field(min_length=1, max_length=10)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
