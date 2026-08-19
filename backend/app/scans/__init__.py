"""Scan subsystem (Modules 3A–3B).

Persistence/domain foundation (3A) plus the execution service and issue
persistence (3B). The service drives the controlled lifecycle through the
repository protocols — never Supabase directly.
"""

from app.scans.exceptions import (
    InvalidScanTransitionError,
    ScanConfigurationError,
    ScanError,
    ScanExecutionError,
    ScanNotFoundError,
)
from app.scans.interfaces import AccessibilityIssueRepository, ScanRepository
from app.scans.models import (
    Scan,
    ScanCreate,
    ScanStatus,
    ScanUpdate,
    StoredAccessibilityIssue,
    assert_valid_transition,
)

__all__ = [
    "AccessibilityIssueRepository",
    "InvalidScanTransitionError",
    "Scan",
    "ScanConfigurationError",
    "ScanCreate",
    "ScanError",
    "ScanExecutionError",
    "ScanNotFoundError",
    "ScanRepository",
    "ScanStatus",
    "ScanUpdate",
    "StoredAccessibilityIssue",
    "assert_valid_transition",
]
