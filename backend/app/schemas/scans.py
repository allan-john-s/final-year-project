"""Request/response schemas for the scans API surface (future routes).

HTTP-layer models mirroring the projects convention: they validate incoming
bodies and shape documented responses, while domain contracts live in
:mod:`app.scans.models`. No routes mount these yet — Module 3A ships the
shapes so the future scanner pipeline can wire them without API changes.

``user_id`` is intentionally absent from every request and response:
ownership is always derived from the authenticated request.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.scanners.models import ScannerType
from app.scans.models import ScanStatus

_URL_MAX = 2048


class ScanCreateRequest(BaseModel):
    """Body for ``POST /api/v1/scans`` (future). ``user_id`` is never accepted
    — ownership always comes from the authenticated request."""

    project_id: str = Field(min_length=1)
    scanner_type: ScannerType
    scan_url: Optional[str] = Field(default=None, max_length=_URL_MAX)


class ScanStartRequest(BaseModel):
    """Body for ``POST /api/v1/projects/{project_id}/scan``.

    ``scanner_type`` defaults to AXE (the only registered engine in 3B); the
    project id lives in the path and ``user_id`` never appears here — both
    are derived from the authenticated request.
    """

    scanner_type: ScannerType = ScannerType.AXE


class ScanUpdateRequest(BaseModel):
    """Body for ``PATCH /api/v1/scans/{id}`` (future) — all fields optional,
    at least one required."""

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


class ScanResponse(BaseModel):
    """A scan as returned by the API (never includes ``user_id``)."""

    id: str
    project_id: str
    scanner_type: ScannerType
    status: ScanStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    total_issues: int = 0
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0
    accessibility_score: Optional[float] = None
    scanner_name: Optional[str] = None
    scanner_version: Optional[str] = None
    wcag_version: Optional[str] = None
    scan_url: Optional[str] = None
    scan_depth: int = 1
    pages_scanned: int = 0
    browser_name: Optional[str] = None
    browser_version: Optional[str] = None
    user_agent: Optional[str] = None
    total_dom_elements: int = 0
    tested_elements: int = 0
    normalization_duration_ms: Optional[int] = None
    persistence_duration_ms: Optional[int] = None
    created_at: datetime
