"""Request/response schemas for accessibility issues.

``IssueResponse`` mirrors a persisted issue row (including row identity)
without exposing anything ownership-related beyond the scan it belongs to.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.scanners.models import Impact, WcagLevel


class IssueResponse(BaseModel):
    """A normalized accessibility issue as returned by the API."""

    id: str
    scan_id: str
    rule_id: str
    rule_name: str
    description: str = ""
    help: str = ""
    help_url: str = ""
    impact: Impact
    wcag_level: Optional[WcagLevel] = None
    tags: List[str] = Field(default_factory=list)
    element_selector: str = ""
    html_snippet: str = ""
    failure_summary: str = ""
    xpath: str = ""
    css_path: str = ""
    dom_path: str = ""
    screenshot_path: str = ""
    created_at: datetime
