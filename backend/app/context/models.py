"""Context Builder domain models (Module 3C).

A :class:`ContextDocument` is a deterministic, machine-readable representation
of *why* an accessibility finding exists and *what surrounds it* — the
evidence future strategy-generation modules will consume. It intentionally
contains no remediation advice, no AI output, and no user secrets.

Every model is explicit (no raw ``dict`` soup) and fully serializable. The
``context_version`` allows the research system to evolve the representation
without breaking consumers (1.0 → 1.1 → 2.0 …).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.projects.models import ProjectStatus
from app.scans.models import ScanStatus
from app.scanners.models import Impact, ScannerType, WcagLevel

CONTEXT_VERSION = "1.0"
"""The current context representation version."""


class ProjectContext(BaseModel):
    """Safe project-level context (never user identity or credentials)."""

    project_id: str
    name: str
    description: str = ""
    website_url: str
    status: ProjectStatus


class ScanContext(BaseModel):
    """How the scan ran and what it found (mirrors the scan row)."""

    scan_id: str
    project_id: str
    scanner_type: ScannerType
    status: ScanStatus
    scanner_name: Optional[str] = None
    scanner_version: Optional[str] = None
    wcag_version: Optional[str] = None
    scan_url: Optional[str] = None
    scan_depth: int = 1
    pages_scanned: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total_dom_elements: int = 0
    tested_elements: int = 0
    accessibility_score: Optional[float] = None
    total_issues: int = 0
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0


class PageContext(BaseModel):
    """Page-level context derived from the scan (single-page in Module 3B)."""

    url: str
    hostname: str = ""
    pathname: str = ""
    title: str = ""  # not captured by the scanner yet — reserved for later
    scanned_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    scanner: Optional[str] = None
    scanner_version: Optional[str] = None
    total_issues: int = 0
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0
    accessibility_score: Optional[float] = None


class WcagContext(BaseModel):
    """WCAG-related context for a rule/issue — only what axe actually reports,
    plus deterministic principle mapping (never invented criteria)."""

    wcag_version: Optional[str] = None
    level: Optional[WcagLevel] = None
    tags: List[str] = Field(default_factory=list)
    criteria: List[str] = Field(default_factory=list)  # e.g. ["1.4.3", "4.1.2"]
    principle: Optional[str] = None  # Perceivable/Operable/Understandable/Robust


class RuleContext(BaseModel):
    """The axe rule behind an issue, with its remediation guidance."""

    rule_id: str
    rule_name: str
    description: str = ""
    help: str = ""
    help_url: str = ""
    impact: Impact
    tags: List[str] = Field(default_factory=list)
    wcag: WcagContext = Field(default_factory=WcagContext)


class ElementContext(BaseModel):
    """Structured view of the affected HTML element (untrusted input —
    callers must treat ``html``/``text_content`` as opaque, escaped text)."""

    html: str = ""
    tag: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    selector: str = ""
    dom_path: str = ""
    text_content: str = ""
    role: Optional[str] = None
    aria: Dict[str, str] = Field(default_factory=dict)
    form: Dict[str, str] = Field(default_factory=dict)
    surrounding_html: str = ""  # not captured by the scanner yet — reserved
    parent_context: str = ""  # not captured by the scanner yet — reserved


class EvidenceContext(BaseModel):
    """Raw evidence preserved verbatim from the normalized issue."""

    failure_summary: str = ""
    xpath: str = ""
    css_path: str = ""
    screenshot_path: str = ""
    affected_nodes: int = 1  # one persisted row per axe node in Module 3B


class IssueContext(BaseModel):
    """One normalized accessibility issue plus its structured context."""

    issue_id: str
    scan_id: str
    project_id: str
    rule: RuleContext
    impact: Impact
    wcag: WcagContext = Field(default_factory=WcagContext)
    element: ElementContext = Field(default_factory=ElementContext)
    evidence: EvidenceContext = Field(default_factory=EvidenceContext)
    scanner_name: str = ""
    scanner_version: str = ""


class IssueGroup(BaseModel):
    """A deterministic, explainable grouping of issues.

    ``group_id`` doubles as the stable sort key (``rule:<rule_id>``,
    ``element:<selector>``, ``wcag:<criterion>``), so ordering is fully
    reproducible across identical inputs.
    """

    group_id: str
    group_type: str  # "same_rule" | "same_element" | "wcag"
    label: str
    issue_ids: List[str] = Field(default_factory=list)


class ContextDocument(BaseModel):
    """The complete, versioned context for one completed scan.

    ``generated_at`` is metadata only — every content field is derived
    deterministically from project + scan + issue rows.
    """

    context_version: str = CONTEXT_VERSION
    project: ProjectContext
    scan: ScanContext
    page: PageContext
    issues: List[IssueContext] = Field(default_factory=list)
    groups: List[IssueGroup] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
