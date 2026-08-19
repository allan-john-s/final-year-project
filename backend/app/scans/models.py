"""Scan domain models.

The persistence contract for the scanning subsystem: a scan belongs to one
project (and therefore one user) and moves through a controlled lifecycle.
HTTP-layer schemas live in :mod:`app.schemas.scans`; these models are the
domain boundary between service, repository, and API layers.

Deliberately small in Module 3A: no execution orchestration yet, just the
shapes the future scanner pipeline will read and write.
"""

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from app.scanners.models import AccessibilityIssue, ScannerType, summarize_issues
from app.scans.exceptions import InvalidScanTransitionError


class ScanStatus(str, enum.Enum):
    """Controlled scan lifecycle state.

    The database CHECK constraint mirrors these exact values so arbitrary
    statuses are rejected at every layer. ``CANCELLED`` is intentionally not
    modelled yet.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_VALID_TRANSITIONS: Dict[ScanStatus, Set[ScanStatus]] = {
    ScanStatus.PENDING: {ScanStatus.RUNNING},
    ScanStatus.RUNNING: {ScanStatus.COMPLETED, ScanStatus.FAILED},
}


def assert_valid_transition(current: ScanStatus, target: ScanStatus) -> None:
    """Raise :class:`InvalidScanTransitionError` unless ``current → target``
    is a legal lifecycle step. The service layer calls this on every status
    change so illegal moves (e.g. PENDING → COMPLETED) are impossible even if
    a repository/route regresses.
    """
    allowed = _VALID_TRANSITIONS.get(current, set())
    if current == target or target not in allowed:
        raise InvalidScanTransitionError(
            f"Cannot move a scan from {current.value} to {target.value}."
        )


_SCAN_URL_MAX = 2048


class Scan(BaseModel):
    """A scan row as stored/retrieved from persistence."""

    id: str
    project_id: str
    user_id: str
    scanner_type: ScannerType
    status: ScanStatus = ScanStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    total_issues: int = Field(default=0, ge=0)
    critical_count: int = Field(default=0, ge=0)
    serious_count: int = Field(default=0, ge=0)
    moderate_count: int = Field(default=0, ge=0)
    minor_count: int = Field(default=0, ge=0)
    accessibility_score: Optional[float] = Field(default=None, ge=0, le=100)

    # --- normalized scanner metadata (mirrors ScanMetadata) -----------------
    scanner_name: Optional[str] = None
    scanner_version: Optional[str] = None
    wcag_version: Optional[str] = None
    scan_url: Optional[str] = Field(default=None, max_length=_SCAN_URL_MAX)
    scan_depth: int = Field(default=1, ge=1)
    pages_scanned: int = Field(default=0, ge=0)
    browser_name: Optional[str] = None
    browser_version: Optional[str] = None
    user_agent: Optional[str] = None
    total_dom_elements: int = Field(default=0, ge=0)
    tested_elements: int = Field(default=0, ge=0)
    normalization_duration_ms: Optional[int] = None
    persistence_duration_ms: Optional[int] = None

    created_at: datetime


class ScanCreate(BaseModel):
    """A fully-resolved create command, including owning user + project.

    ``user_id`` always comes from the authenticated request (never the body);
    the repository writes both ids so ownership is stored at insert time and
    enforced on every later query.
    """

    user_id: str
    project_id: str
    scanner_type: ScannerType
    status: ScanStatus = ScanStatus.PENDING
    scan_url: Optional[str] = Field(default=None, max_length=_SCAN_URL_MAX)

    def with_result(self, result) -> "ScanCreate":
        """Attach a normalized scan result's metadata to this command.

        Used by the future pipeline to persist a completed scan with its
        full metadata. Kept separate so creating a scan never requires a
        result.
        """
        metadata = result.metadata
        summary = result.summary()
        return self.model_copy(
            update={
                "status": ScanStatus.COMPLETED,
                "summary": summary.model_dump(),
                "total_issues": summary.total_issues,
                "critical_count": summary.critical_count,
                "serious_count": summary.serious_count,
                "moderate_count": summary.moderate_count,
                "minor_count": summary.minor_count,
                "scanner_name": metadata.scanner_name,
                "scanner_version": metadata.scanner_version,
                "wcag_version": metadata.wcag_version,
                "scan_url": metadata.scan_url,
                "scan_depth": metadata.scan_depth,
                "pages_scanned": metadata.pages_scanned,
                "browser_name": metadata.browser_name,
                "browser_version": metadata.browser_version,
                "user_agent": metadata.user_agent,
                "total_dom_elements": metadata.total_dom_elements,
                "tested_elements": metadata.tested_elements,
                "normalization_duration_ms": result.timing.normalization_duration_ms,
                "duration_ms": result.timing.duration_ms,
            }
        )


class ScanUpdate(BaseModel):
    """Partial update; ``None`` fields are left unchanged."""

    status: Optional[ScanStatus] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    summary: Optional[Dict[str, Any]] = None
    total_issues: Optional[int] = Field(default=None, ge=0)
    critical_count: Optional[int] = Field(default=None, ge=0)
    serious_count: Optional[int] = Field(default=None, ge=0)
    moderate_count: Optional[int] = Field(default=None, ge=0)
    minor_count: Optional[int] = Field(default=None, ge=0)
    accessibility_score: Optional[float] = Field(default=None, ge=0, le=100)
    scanner_name: Optional[str] = None
    scanner_version: Optional[str] = None
    wcag_version: Optional[str] = None
    scan_url: Optional[str] = Field(default=None, max_length=_SCAN_URL_MAX)
    scan_depth: Optional[int] = Field(default=None, ge=1)
    pages_scanned: Optional[int] = Field(default=None, ge=0)
    browser_name: Optional[str] = None
    browser_version: Optional[str] = None
    user_agent: Optional[str] = None
    total_dom_elements: Optional[int] = Field(default=None, ge=0)
    tested_elements: Optional[int] = Field(default=None, ge=0)
    normalization_duration_ms: Optional[int] = Field(default=None, ge=0)
    persistence_duration_ms: Optional[int] = Field(default=None, ge=0)

    def from_result(self, result) -> "ScanUpdate":
        """Build an update carrying a completed scan's metadata + counts.

        Convenience for the future pipeline: persists everything a
        :class:`NormalizedScanResult` produces in one call.
        """
        metadata = result.metadata
        summary = summarize_issues(result.issues)
        return ScanUpdate(
            status=ScanStatus.COMPLETED,
            duration_ms=result.timing.duration_ms,
            summary=summary.model_dump(),
            total_issues=summary.total_issues,
            critical_count=summary.critical_count,
            serious_count=summary.serious_count,
            moderate_count=summary.moderate_count,
            minor_count=summary.minor_count,
            scanner_name=metadata.scanner_name,
            scanner_version=metadata.scanner_version,
            wcag_version=metadata.wcag_version,
            scan_url=metadata.scan_url,
            scan_depth=metadata.scan_depth,
            pages_scanned=metadata.pages_scanned,
            browser_name=metadata.browser_name,
            browser_version=metadata.browser_version,
            user_agent=metadata.user_agent,
            total_dom_elements=metadata.total_dom_elements,
            tested_elements=metadata.tested_elements,
            normalization_duration_ms=result.timing.normalization_duration_ms,
        )


class StoredAccessibilityIssue(AccessibilityIssue):
    """An accessibility issue row as persisted/retrieved — adds row identity
    (``id``, ``scan_id``, ``created_at``) to the normalized contract."""

    id: str
    scan_id: str
    created_at: datetime

