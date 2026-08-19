"""Strategy domain models (Module 4).

A :class:`CandidateStrategy` is one *candidate* remediation alternative for a
selected accessibility issue or deterministic issue group. The generator
produces 2–5 genuinely distinct candidates; choosing among them is explicitly
out of scope until the later evaluation/ranking modules.

The pipeline is fully typed — no ``dict`` soup:

``ContextDocument`` → :class:`StrategyTarget` → provider
→ ``List[CandidateStrategy]`` → validated → :class:`StrategyGeneration`

``StrategyGenerationMetadata`` carries research traceability (scan, target,
context/prompt version, provider, model, settings) and is guaranteed to never
contain credentials or user secrets.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.context.models import IssueContext


class StrategyType(str, Enum):
    """Controlled strategy families.

    The generator prefers native semantic HTML; ARIA is only suggested when
    the specific context justifies it.
    """

    NATIVE_HTML = "native_html"
    ARIA = "aria"
    STRUCTURAL = "structural"
    CONTENT = "content"
    BEHAVIORAL = "behavioral"
    VISUAL = "visual"
    ALTERNATIVE = "alternative"
    OTHER = "other"


class EffortRating(str, Enum):
    """Controlled implementation-effort rating."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImpactRating(str, Enum):
    """Controlled expected-accessibility-impact rating."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CandidateStrategy(BaseModel):
    """One validated candidate remediation strategy.

    Every field is explicit and bounded; the model doubles as the structured
    output contract the LLM provider must satisfy.
    """

    strategy_id: str = Field(min_length=1, max_length=64)
    strategy_index: int = Field(ge=1, le=5)
    issue_id: str = Field(min_length=1, max_length=64)
    group_id: Optional[str] = Field(default=None, max_length=128)
    context_version: str = Field(min_length=1, max_length=16)
    strategy_type: StrategyType
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    implementation_steps: List[str] = Field(min_length=1, max_length=20)
    expected_accessibility_impact: ImpactRating
    wcag_alignment: List[str] = Field(default_factory=list, max_length=20)
    implementation_effort: EffortRating
    maintainability_notes: str = Field(default="", max_length=2000)
    compatibility_notes: str = Field(default="", max_length=2000)
    risks: List[str] = Field(default_factory=list, max_length=20)
    assumptions: List[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_reference: str = Field(default="", max_length=128)

    @field_validator(
        "title",
        "summary",
        "rationale",
        "maintainability_notes",
        "compatibility_notes",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("implementation_steps", "risks", "assumptions", mode="before")
    @classmethod
    def _strip_list_items(cls, value: object) -> object:
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return value

    @field_validator("wcag_alignment", mode="before")
    @classmethod
    def _normalize_wcag(cls, value: object) -> object:
        if isinstance(value, list):
            return sorted({str(item).strip() for item in value if str(item).strip()})
        return value


class StrategyTarget(BaseModel):
    """The resolved generation target: one issue or one deterministic group.

    ``issues`` always contains the concrete :class:`IssueContext`(s) so
    providers can reason over real rule/WCAG/element evidence — the mock
    provider needs it, and the prompt builder serializes it.
    """

    target_type: str  # "issue" | "group"
    issue_id: Optional[str] = None
    group_id: Optional[str] = None
    issues: List[IssueContext] = Field(default_factory=list)


class StrategyGenerationRequest(BaseModel):
    """The complete, self-contained input handed to a provider.

    Providers are stateless: everything they need (versioned prompts plus the
    resolved target) travels in this request.
    """

    prompt_version: str
    context_version: str
    system_prompt: str
    user_prompt: str
    target: StrategyTarget
    model: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=16000)
    strategy_count: int = Field(ge=2, le=5)


class StrategyGenerationMetadata(BaseModel):
    """Research traceability for one generation call.

    Contains no credentials, tokens, or user identity — only identifiers and
    generation settings needed to reproduce an experiment as far as the
    provider allows.
    """

    scan_id: str
    target_type: str
    issue_id: Optional[str] = None
    group_id: Optional[str] = None
    context_version: str
    prompt_version: str
    provider: str
    model: str
    temperature: float
    strategy_count: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyGeneration(BaseModel):
    """The API result: traceable metadata plus validated candidate strategies."""

    metadata: StrategyGenerationMetadata
    strategies: List[CandidateStrategy] = Field(min_length=2, max_length=5)
