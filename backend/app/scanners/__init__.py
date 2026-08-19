"""Scanner subsystem (Modules 3A–3B).

Architecture + normalized domain models (3A) and the first real engine —
:class:`AxeScanner` via Playwright (3B). The API/service layers consume
:class:`BaseScanner` through the factory registry, never a concrete engine.
"""

from app.scanners.base import BaseScanner
from app.scanners.exceptions import (
    ScannerConfigurationError,
    ScannerError,
    ScannerRuntimeError,
    ScannerTargetError,
)
from app.scanners.factory import ScannerUnavailableError, available_scanners, get_scanner
from app.scanners.models import (
    AccessibilityIssue,
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScannerType,
    ScanSummary,
    ScanTiming,
    WcagLevel,
    calculate_accessibility_score,
    summarize_issues,
)

__all__ = [
    "AccessibilityIssue",
    "BaseScanner",
    "Impact",
    "NormalizedScanResult",
    "ScanMetadata",
    "ScannerConfigurationError",
    "ScannerError",
    "ScannerRuntimeError",
    "ScannerTargetError",
    "ScannerType",
    "ScannerUnavailableError",
    "ScanSummary",
    "ScanTiming",
    "WcagLevel",
    "available_scanners",
    "calculate_accessibility_score",
    "get_scanner",
    "summarize_issues",
]
