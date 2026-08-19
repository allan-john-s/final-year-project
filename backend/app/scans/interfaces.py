"""Scan repository contract.

The persistence boundary for scans — the only place that talks to storage.
Services and future routes depend on this protocol, never on a concrete
implementation, so tests can inject an in-memory fake and future storage
backends slot in unchanged.

Every method takes the owning ``user_id`` explicitly; implementations MUST
scope their queries to that user so ownership is enforced at the data layer
(not just in route code) — the same defense-in-depth as projects.
"""

from typing import List, Optional, Protocol

from app.scans.models import Scan, ScanCreate, ScanUpdate, StoredAccessibilityIssue
from app.scanners.models import AccessibilityIssue


class ScanRepository(Protocol):
    """Data access for scans, always scoped to a single user."""

    async def create(self, data: ScanCreate) -> Scan:
        """Persist a new scan (owned by ``data.user_id``) and return it."""
        ...

    async def get(self, user_id: str, scan_id: str) -> Optional[Scan]:
        """Return ``scan_id`` if owned by ``user_id``, else ``None``."""
        ...

    async def list_for_project(self, user_id: str, project_id: str) -> list[Scan]:
        """Return ``user_id``'s scans for ``project_id``, newest first."""
        ...

    async def list_for_user(self, user_id: str) -> list[Scan]:
        """Return every scan owned by ``user_id``, newest first."""
        ...

    async def update(
        self,
        user_id: str,
        scan_id: str,
        changes: ScanUpdate,
    ) -> Optional[Scan]:
        """Apply ``changes`` to ``scan_id`` if owned; return it or ``None``."""
        ...

    async def delete(self, user_id: str, scan_id: str) -> bool:
        """Delete ``scan_id`` if owned; return whether a row was removed."""
        ...


class AccessibilityIssueRepository(Protocol):
    """Data access for normalized accessibility issues, owned via their scan."""

    async def insert_many(self, scan_id: str, issues: List[AccessibilityIssue]) -> int:
        """Persist ``issues`` under ``scan_id``; return the number written."""
        ...

    async def list_for_scan(self, user_id: str, scan_id: str) -> List[StoredAccessibilityIssue]:
        """Return the issues of ``scan_id`` only if the caller owns that scan
        (ownership enforced in the query itself, like the scan repository)."""
        ...
