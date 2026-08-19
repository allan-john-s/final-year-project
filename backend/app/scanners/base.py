"""Scanner engine abstraction.

:class:`BaseScanner` is the contract every scanner engine (Axe, Lighthouse,
Pa11y, WAVE, a custom research scanner) must implement. The API, service, and
persistence layers depend on this interface — never on a concrete engine — so
adding a new scanner is purely a registration concern (see
:mod:`app.scanners.factory`).

Module 3A ships the contract only; no concrete engine is implemented yet.
"""

from abc import ABC, abstractmethod

from app.scanners.models import NormalizedScanResult, ScannerType


class BaseScanner(ABC):
    """A scanner that turns a target URL into a :class:`NormalizedScanResult`."""

    # --- identity (each concrete scanner overrides these) -------------------

    name: str
    """Human-readable scanner name, e.g. ``"axe-core"``."""

    version: str
    """Scanner engine version, e.g. ``"4.10.2"``."""

    wcag_version: str
    """WCAG version the scanner targets, e.g. ``"2.2"``."""

    scanner_type: ScannerType
    """Controlled identifier used for persistence and dispatch."""

    # --- contract -----------------------------------------------------------

    @abstractmethod
    async def scan(self, url: str, *, depth: int = 1) -> NormalizedScanResult:
        """Scan ``url`` and return the normalized result.

        Implementations MUST:

        - treat ``url`` as the entry point of the scan,
        - populate :class:`ScanMetadata` with their own identity plus the
          execution environment,
        - normalize every finding into :class:`AccessibilityIssue`,
        - raise a documented exception rather than returning partial results
          when the scan cannot complete.

        ``depth`` controls how many levels of linked pages are scanned
        (default 1 = the single page).
        """
        ...
