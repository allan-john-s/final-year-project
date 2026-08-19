"""Evaluation domain models (Module 5).

A :class:`StrategyEvaluation` is the *independent, multidimensional* result
of evaluating ONE candidate remediation strategy against the accessibility
context of a completed scan.

Research separation (deliberate):

- Module 4 *generates* multiple alternatives (:class:`CandidateStrategy`).
- Module 5 *evaluates* every alternative independently across seven
  bounded 0–10 dimensions (:class:`StrategyEvaluation`).
- Ranking / winner selection belongs to Module 6 and is intentionally NOT
  represented here — there is no ``total_score`` and no ``rank`` field.

Score semantics (documented, never inverted):

- Positive criteria (accessibility impact, standards compliance, contextual
  suitability, maintainability, compatibility): 10 = excellent, 0 = extremely
  poor.
- Implementation effort: 10 = very easy / very low effort, 0 = extremely
  difficult / very high effort.
- Risk: 10 = very low risk, 0 = very high risk.

The provider produces an :class:`EvaluationDraft` (the seven scores plus
qualitative reasoning); the service stamps the research traceability
(scan/issue/group ids, versions, provider/model, timestamp) into the final
:class:`StrategyEvaluation`.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.strategies.models import CandidateStrategy, StrategyTarget

EVALUATION_VERSION = "1.0"
"""The current evaluation representation version."""

# The seven evaluation dimensions, in display order.
EVALUATION_CRITERIA = [
    "accessibility_impact_score",
    "standards_compliance_score",
    "contextual_suitability_score",
    "implementation_effort_score",
    "maintainability_score",
    "compatibility_score",
    "risk_score",
]
"""Controlled list of the evaluation criteria (see module docstring for
score semantics)."""


def _strip_list_items(value: object) -> object:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return value


class EvaluationDraft(BaseModel):
    """The provider-produced part of an evaluation.

    Everything here is *content*: the seven bounded scores plus qualitative
    reasoning. Traceability (scan/issue/group ids, versions, provider, model,
    timestamp) is stamped by the service, so providers stay stateless.
    """

    strategy_id: str = Field(min_length=1, max_length=64)
    accessibility_impact_score: int = Field(ge=0, le=10)
    standards_compliance_score: int = Field(ge=0, le=10)
    contextual_suitability_score: int = Field(ge=0, le=10)
    implementation_effort_score: int = Field(ge=0, le=10)
    maintainability_score: int = Field(ge=0, le=10)
    compatibility_score: int = Field(ge=0, le=10)
    risk_score: int = Field(ge=0, le=10)
    strengths: List[str] = Field(min_length=1, max_length=10)
    weaknesses: List[str] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=1, max_length=4000)
    assumptions: List[str] = Field(default_factory=list, max_length=10)
    uncertainties: List[str] = Field(default_factory=list, max_length=10)
    evidence_references: List[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "rationale",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "strengths",
        "weaknesses",
        "assumptions",
        "uncertainties",
        "evidence_references",
        mode="before",
    )
    @classmethod
    def _strip_list(cls, value: object) -> object:
        return _strip_list_items(value)


class StrategyEvaluation(EvaluationDraft):
    """One complete, traceable evaluation of a single candidate strategy.

    Intentionally has NO ``total_score`` and NO ``rank`` — Module 5 produces
    multidimensional evidence; Module 6 decides how to combine it.
    """

    evaluation_id: str = Field(min_length=1, max_length=128)
    scan_id: str = Field(min_length=1, max_length=64)
    issue_id: str = Field(min_length=1, max_length=64)
    group_id: Optional[str] = Field(default=None, max_length=128)
    context_version: str = Field(min_length=1, max_length=16)
    evaluation_version: str = EVALUATION_VERSION
    evaluator_provider: str = Field(min_length=1, max_length=32)
    evaluator_model: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=16)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyEvaluationRequest(BaseModel):
    """The complete, self-contained input handed to an evaluator provider.

    Providers are stateless: the versioned prompts plus the strategy being
    evaluated and the resolved target evidence travel in this request.
    """

    prompt_version: str
    evaluation_version: str
    context_version: str
    system_prompt: str
    user_prompt: str
    strategy: CandidateStrategy
    target: StrategyTarget
    model: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=16000)


class EvaluationBatch(BaseModel):
    """The API result: traceable batch metadata plus one evaluation per
    supplied strategy (each independent — no ranking, no total)."""

    scan_id: str
    issue_id: Optional[str] = None
    group_id: Optional[str] = None
    context_version: str
    evaluation_version: str = EVALUATION_VERSION
    prompt_version: str
    provider: str
    model: str
    evaluations: List[StrategyEvaluation] = Field(min_length=1, max_length=10)
