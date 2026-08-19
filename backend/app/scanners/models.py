"""Normalized scanner domain models.

Every future scanner (Axe, Lighthouse, Pa11y, WAVE, a custom research
scanner) must return a :class:`NormalizedScanResult` — the single contract
between scanner engines and the rest of the application. The API, service,
and persistence layers depend on these models, never on a concrete engine.

The structure is deliberately kept free of AI/context fields: it is the
foundation the future Context Builder will consume, so every piece of raw
information a scanner can produce is typed here.
"""

import enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

_SCAN_URL_MAX = 2048


class ScannerType(str, enum.Enum):
    """Controlled identifiers for supported scanner engines."""

    AXE = "AXE"
    LIGHTHOUSE = "LIGHTHOUSE"
    PA11Y = "PA11Y"
    WAVE = "WAVE"
    RESEARCH = "RESEARCH"


class Impact(str, enum.Enum):
    """Controlled severity representation (mirrors axe impact levels)."""

    CRITICAL = "CRITICAL"
    SERIOUS = "SERIOUS"
    MODERATE = "MODERATE"
    MINOR = "MINOR"


class WcagLevel(str, enum.Enum):
    """WCAG conformance levels a rule can map to."""

    A = "A"
    AA = "AA"
    AAA = "AAA"


class ScanMetadata(BaseModel):
    """Metadata describing how a scan was executed.

    Mirrors the ``scans`` table columns so a normalized result can be
    persisted without lossy translation.
    """

    scanner_name: str = Field(min_length=1, max_length=100)
    scanner_type: ScannerType
    scanner_version: str = Field(min_length=1, max_length=50)
    wcag_version: str = Field(min_length=1, max_length=10)
    scan_url: str = Field(min_length=1, max_length=_SCAN_URL_MAX)
    scan_depth: int = Field(default=1, ge=1)
    pages_scanned: int = Field(default=1, ge=0)
    browser_name: Optional[str] = Field(default=None, max_length=100)
    browser_version: Optional[str] = Field(default=None, max_length=50)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    total_dom_elements: int = Field(default=0, ge=0)
    tested_elements: int = Field(default=0, ge=0)

    @field_validator("scan_url")
    @classmethod
    def _validate_scan_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("scan_url must not be empty.")
        if not stripped.lower().startswith(("http://", "https://")):
            raise ValueError("scan_url must start with http:// or https://.")
        if any(char.isspace() for char in stripped):
            raise ValueError("scan_url must not contain whitespace.")
        return stripped


class ScanTiming(BaseModel):
    """Timing metadata for a normalized scan result (milliseconds)."""

    duration_ms: int = Field(default=0, ge=0)
    normalization_duration_ms: int = Field(default=0, ge=0)


class AccessibilityIssue(BaseModel):
    """A single normalized accessibility issue.

    Structured for future Context Builder input: every field a scanner
    reports about a finding is preserved in a typed, serializable form.
    """

    rule_id: str = Field(min_length=1, max_length=100)
    rule_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    help: str = Field(default="", max_length=2000)
    help_url: str = Field(default="", max_length=2048)
    impact: Impact
    wcag_level: Optional[WcagLevel] = None
    tags: List[str] = Field(default_factory=list)
    element_selector: str = Field(default="", max_length=2000)
    html_snippet: str = Field(default="", max_length=8000)
    failure_summary: str = Field(default="", max_length=4000)
    xpath: str = Field(default="", max_length=4000)
    css_path: str = Field(default="", max_length=4000)
    dom_path: str = Field(default="", max_length=4000)
    screenshot_path: str = Field(default="", max_length=2048)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: List[str]) -> List[str]:
        cleaned = [tag.strip() for tag in value if tag and tag.strip()]
        if len(cleaned) != len(value):
            raise ValueError("tags must not contain empty values.")
        return cleaned


class ScanSummary(BaseModel):
    """Aggregated issue counts, computed from a scan's issues."""

    total_issues: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    serious_count: int = Field(ge=0)
    moderate_count: int = Field(ge=0)
    minor_count: int = Field(ge=0)


def calculate_accessibility_score(issues: List[AccessibilityIssue]) -> float:
    """Score a scan 0–100 (100 = no findings).

    Deterministic weighted penalty per impact level, clamped to [0, 100]:
    critical −10, serious −5, moderate −2, minor −1. Simple, explainable,
    and stable across runs — deliberately not a machine-learning score.
    """
    if not issues:
        return 100.0
    summary = summarize_issues(issues)
    penalty = (
        10 * summary.critical_count
        + 5 * summary.serious_count
        + 2 * summary.moderate_count
        + 1 * summary.minor_count
    )
    return round(max(0.0, min(100.0, 100.0 - penalty)), 2)


def summarize_issues(issues: List[AccessibilityIssue]) -> ScanSummary:
    """Count issues per impact level for persistence/display."""
    counts = {Impact.CRITICAL: 0, Impact.SERIOUS: 0, Impact.MODERATE: 0, Impact.MINOR: 0}
    for issue in issues:
        counts[issue.impact] += 1
    return ScanSummary(
        total_issues=len(issues),
        critical_count=counts[Impact.CRITICAL],
        serious_count=counts[Impact.SERIOUS],
        moderate_count=counts[Impact.MODERATE],
        minor_count=counts[Impact.MINOR],
    )


class NormalizedScanResult(BaseModel):
    """The normalized output of any scanner — the domain contract.

    ``metadata`` describes how the scan ran, ``timing`` how long it took,
    and ``issues`` the normalized findings. Summary counts are derived from
    ``issues`` via :meth:`summary` so they can never disagree with the data.
    """

    metadata: ScanMetadata
    timing: ScanTiming = Field(default_factory=ScanTiming)
    issues: List[AccessibilityIssue] = Field(default_factory=list)

    def summary(self) -> ScanSummary:
        """Aggregate issue counts for persistence."""
        return summarize_issues(self.issues)
