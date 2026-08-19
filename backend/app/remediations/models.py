"""Remediation domain models (Module 7).

A :class:`RemediationProposal` is a structured, reviewable proposal for fixing
one accessibility issue based on the recommended strategy from Module 6.

Research separation (deliberate):

- Module 4 *generates* candidate strategies.
- Module 5 *evaluates* those strategies.
- Module 6 *ranks* the evaluated strategies.
- Module 7 *proposes* a concrete remediation for the top-ranked strategy.

Module 7 does NOT:

- Modify source code automatically.
- Create commits or pull requests.
- Perform re-scans.

The proposal is a REVIEW-FIRST artifact — the developer decides whether
to accept and apply it.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

REMEDIATION_VERSION = "1.0"
"""The current remediation representation version."""


class RemediationStatus(str, Enum):
    """Controlled lifecycle for remediation proposals.

    Valid transitions:
    - PROPOSED → REVIEWED
    - REVIEWED → ACCEPTED
    - REVIEWED → REJECTED
    - ACCEPTED → APPLIED
    """

    PROPOSED = "PROPOSED"
    REVIEWED = "REVIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


# Valid status transitions — enforced by the service.
_VALID_TRANSITIONS = {
    RemediationStatus.PROPOSED: {RemediationStatus.REVIEWED},
    RemediationStatus.REVIEWED: {RemediationStatus.ACCEPTED, RemediationStatus.REJECTED},
    RemediationStatus.ACCEPTED: {RemediationStatus.APPLIED},
    RemediationStatus.REJECTED: set(),
    RemediationStatus.APPLIED: set(),
}


def is_valid_transition(current: RemediationStatus, target: RemediationStatus) -> bool:
    """Check if a status transition is valid."""
    return target in _VALID_TRANSITIONS.get(current, set())


class ProposedChange(BaseModel):
    """A proposed source-code change — BEFORE and AFTER.

    This is a review artifact only. The application does NOT automatically
    modify files.
    """

    before: str = Field(min_length=1, max_length=10000)
    after: str = Field(min_length=1, max_length=10000)
    file_path: Optional[str] = Field(default=None, max_length=500)
    line_number: Optional[int] = Field(default=None, ge=1)
    explanation: str = Field(min_length=1, max_length=2000)


class RemediationProposal(BaseModel):
    """A structured, reviewable remediation proposal for one accessibility issue.

    Contains everything a developer needs to understand, evaluate, and decide
    whether to apply the proposed fix.
    """

    id: str = Field(min_length=1, max_length=128)
    scan_id: str = Field(min_length=1, max_length=64)
    issue_id: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=64)
    rank: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    implementation_steps: List[str] = Field(min_length=1, max_length=20)
    proposed_change: ProposedChange
    affected_element: str = Field(default="", max_length=2000)
    expected_improvement: str = Field(min_length=1, max_length=2000)
    risks: List[str] = Field(default_factory=list, max_length=20)
    validation_steps: List[str] = Field(min_length=1, max_length=20)
    provider: str = Field(min_length=1, max_length=32)
    confidence: float = Field(ge=0.0, le=1.0)
    status: RemediationStatus = RemediationStatus.PROPOSED
    remediation_version: str = REMEDIATION_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator(
        "title",
        "summary",
        "rationale",
        "expected_improvement",
        "affected_element",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("implementation_steps", "risks", "validation_steps", mode="before")
    @classmethod
    def _strip_list_items(cls, value: object) -> object:
        if isinstance(value, list):
            return [
                item.strip() for item in value if isinstance(item, str) and item.strip()
            ]
        return value


class RemediationRequest(BaseModel):
    """Input for generating a remediation proposal.

    Identifies the scan, issue, and strategy to remediate. The service
    validates ownership and associations.
    """

    issue_id: str = Field(min_length=1, max_length=64)
    strategy_id: str = Field(min_length=1, max_length=64)


class RemediationStatusUpdate(BaseModel):
    """Input for updating a proposal's status.

    Only valid transitions are accepted.
    """

    status: RemediationStatus
