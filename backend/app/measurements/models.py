"""Measurement domain models (Module 8).

An :class:`ImprovementMeasurement` compares an original scan against a
follow-up scan after an accepted remediation has been externally applied.

Research separation (deliberate):

- Module 7 *proposes* a remediation (review-first workflow).
- Module 8 *measures* whether the remediation actually improved accessibility
  by comparing actual scan data before and after.

Module 8 does NOT:
- Modify source code.
- Create commits or pull requests.
- Use LLMs for comparison (deterministic, data-driven).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

MEASUREMENT_VERSION = "1.0"
"""The current measurement representation version."""


class MeasurementStatus(str, Enum):
    """Lifecycle for improvement measurements.

    Classification rules (deterministic, documented):
    - IMPROVED: score_delta > 0 AND no severe new issues introduced
    - NO_CHANGE: |score_delta| <= threshold AND no severity regression
    - REGRESSED: score_delta < 0 OR significant new severe issues
    - COMPLETED: measurement performed but result is ambiguous
    """

    IMPROVED = "IMPROVED"
    NO_CHANGE = "NO_CHANGE"
    REGRESSED = "REGRESSED"
    COMPLETED = "COMPLETED"


class SeverityDelta(BaseModel):
    """Before/after counts for a single severity level."""

    severity: str = Field(min_length=1, max_length=16)  # critical/serious/moderate/minor
    before: int = Field(ge=0)
    after: int = Field(ge=0)

    @property
    def delta(self) -> int:
        """Positive = more issues after, negative = fewer issues after."""
        return self.after - self.before


class IssueFingerprint(BaseModel):
    """Stable identity for an accessibility issue, used for cross-scan comparison.

    Fingerprint is derived deterministically from rule_id + element selector
    + (optionally) DOM path. When all three match, the issue is considered
    the same across scans.
    """

    rule_id: str = Field(min_length=1, max_length=100)
    selector: str = Field(default="", max_length=2000)
    dom_path: str = Field(default="", max_length=4000)
    impact: str = Field(default="", max_length=16)
    fingerprint: str = Field(min_length=1, max_length=512)

    @classmethod
    def from_issue_data(
        cls,
        rule_id: str,
        selector: str = "",
        dom_path: str = "",
        impact: str = "",
    ) -> "IssueFingerprint":
        """Create a stable fingerprint from issue fields.

        The fingerprint is a deterministic hash of rule_id + selector + dom_path.
        Two issues with the same rule and element produce the same fingerprint.
        """
        import hashlib

        key = f"{rule_id}|{selector}|{dom_path}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return cls(
            rule_id=rule_id,
            selector=selector,
            dom_path=dom_path,
            impact=impact,
            fingerprint=digest,
        )


class ImprovementMeasurement(BaseModel):
    """A before/after comparison of two scans linked to an accepted remediation.

    Contains all data needed for the research evaluation: score comparison,
    issue-level comparison (resolved/persistent/new), severity breakdown,
    and an objective classification of the outcome.
    """

    id: str = Field(min_length=1, max_length=128)
    remediation_id: str = Field(min_length=1, max_length=128)
    original_scan_id: str = Field(min_length=1, max_length=64)
    followup_scan_id: str = Field(min_length=1, max_length=64)

    # Score comparison
    original_accessibility_score: Optional[float] = Field(default=None, ge=0, le=100)
    followup_accessibility_score: Optional[float] = Field(default=None, ge=0, le=100)
    score_delta: Optional[float] = Field(default=None)
    score_improvement_percentage: Optional[float] = Field(default=None)

    # Issue count comparison
    original_issue_count: int = Field(ge=0)
    followup_issue_count: int = Field(ge=0)
    issues_resolved: int = Field(ge=0)
    issues_remaining: int = Field(ge=0)
    new_issues_introduced: int = Field(ge=0)

    # Severity comparison
    critical_before: int = Field(ge=0)
    critical_after: int = Field(ge=0)
    serious_before: int = Field(ge=0)
    serious_after: int = Field(ge=0)
    moderate_before: int = Field(ge=0)
    moderate_after: int = Field(ge=0)
    minor_before: int = Field(ge=0)
    minor_after: int = Field(ge=0)

    # Outcome
    status: MeasurementStatus
    measurement_summary: str = Field(min_length=1, max_length=4000)

    measurement_version: str = MEASUREMENT_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SeverityBurden(BaseModel):
    """Weighted severity burden score for comparing scan severity profiles.

    Uses the same penalties as the accessibility score calculation:
    critical=10, serious=5, moderate=2, minor=1.
    """

    critical: int = Field(ge=0)
    serious: int = Field(ge=0)
    moderate: int = Field(ge=0)
    minor: int = Field(ge=0)

    @property
    def total_burden(self) -> int:
        """Weighted burden score — lower is better (fewer/severe issues)."""
        return self.critical * 10 + self.serious * 5 + self.moderate * 2 + self.minor * 1

    @property
    def total_issues(self) -> int:
        return self.critical + self.serious + self.moderate + self.minor
