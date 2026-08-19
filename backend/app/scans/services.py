"""Scan execution service.

Orchestrates the full scan lifecycle through the repository protocols — the
service never talks to Supabase (or Playwright/axe) directly:

```
PENDING ──start──▶ RUNNING ──execute──▶ COMPLETED
                        │
                        └──failure──▶ FAILED
```

Responsibilities:

- **Ownership** — every operation is scoped to the authenticated ``user_id``
  passed in by the route; projects are verified before a scan can start and
  list/get/delete all resolve to 404 for anything not owned (IDOR-safe).
- **Lifecycle** — transitions are validated via
  :func:`app.scans.models.assert_valid_transition` so illegal moves are
  impossible even if a repository/route regresses.
- **Execution** — selects the scanner through the factory (never a concrete
  engine), runs it, persists normalized issues, then persists the completed
  scan with counts/score/metadata/timing.
- **Failure** — any scanner/persistence failure marks the row FAILED with a
  sanitized message in ``summary.error`` and re-raises as
  :class:`ScanExecutionError` (no raw exception details leak to clients).

:meth:`run_scan` is the background wrapper: it swallows the error (the row is
the source of truth) so a failed scan never crashes the request cycle.
"""

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import List

from app.projects.exceptions import ProjectNotFoundError
from app.projects.interfaces import ProjectRepository
from app.scans.exceptions import (
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
from app.scanners.factory import ScannerUnavailableError, get_scanner
from app.scanners.models import ScannerType, calculate_accessibility_score

logger = logging.getLogger(__name__)

_MAX_FAILURE_MESSAGE = 2000


def sanitize_failure_message(error: Exception) -> str:
    """Collapse whitespace and truncate a failure for storage/display — never
    a multi-line stack trace or raw internal details."""
    message = " ".join(str(error).split()).strip()
    if not message:
        message = "The scan failed for an unknown reason."
    return message[:_MAX_FAILURE_MESSAGE]


class ScanExecutionService:
    """The scan pipeline: start (PENDING → RUNNING), execute, fail safely."""

    def __init__(
        self,
        scans: ScanRepository,
        issues: AccessibilityIssueRepository,
        projects: ProjectRepository,
    ) -> None:
        self._scans = scans
        self._issues = issues
        self._projects = projects

    # --- public API (routes) ----------------------------------------------

    async def start_scan(
        self,
        user_id: str,
        project_id: str,
        scanner_type: ScannerType = ScannerType.AXE,
    ) -> Scan:
        """Validate the project is owned + the engine is registered, then
        create the scan as PENDING and move it to RUNNING."""
        try:
            get_scanner(scanner_type)
        except ScannerUnavailableError as exc:
            raise ScanConfigurationError(str(exc)) from exc

        project = await self._projects.get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError("Project not found.")

        created = await self._scans.create(
            ScanCreate(
                user_id=user_id,
                project_id=project_id,
                scanner_type=scanner_type,
                scan_url=project.website_url,
            )
        )
        assert_valid_transition(created.status, ScanStatus.RUNNING)

        running = await self._scans.update(
            user_id,
            created.id,
            ScanUpdate(status=ScanStatus.RUNNING, started_at=datetime.now(timezone.utc)),
        )
        if running is None:
            raise ScanError("The scan could not be started.")
        return running

    async def run_scan(self, user_id: str, scan_id: str) -> None:
        """Background-task wrapper — logs failures instead of re-raising; the
        scan row (COMPLETED or FAILED) is the source of truth."""
        try:
            await self.execute_scan(user_id, scan_id)
        except Exception:
            logger.exception("Scan %s failed; the row has been marked FAILED.", scan_id)

    async def execute_scan(self, user_id: str, scan_id: str) -> Scan:
        """Run the scanner for a RUNNING scan and persist the outcome.

        On success the scan becomes COMPLETED with metadata/counts/score; on
        any failure it becomes FAILED (with a sanitized ``summary.error``) and
        :class:`ScanExecutionError` is raised.
        """
        scan = await self._scans.get(user_id, scan_id)
        if scan is None:
            raise ScanNotFoundError("Scan not found.")
        assert_valid_transition(scan.status, ScanStatus.COMPLETED)  # must be RUNNING

        try:
            scanner = get_scanner(scan.scanner_type)
            result = await scanner.scan(scan.scan_url or "", depth=scan.scan_depth)

            persist_started = perf_counter()
            await self._issues.insert_many(scan.id, result.issues)
            persistence_ms = round((perf_counter() - persist_started) * 1000)

            update = ScanUpdate().from_result(result)
            update.accessibility_score = calculate_accessibility_score(result.issues)
            update.completed_at = datetime.now(timezone.utc)
            update.persistence_duration_ms = persistence_ms

            completed = await self._scans.update(user_id, scan_id, update)
            if completed is None:
                raise ScanExecutionError("The completed scan could not be persisted.")
            return completed
        except ScanExecutionError:
            raise
        except Exception as exc:
            await self._mark_failed(user_id, scan_id, exc)
            raise ScanExecutionError(sanitize_failure_message(exc)) from exc

    async def list_for_user(self, user_id: str) -> List[Scan]:
        """Every scan owned by ``user_id``, newest first."""
        return await self._scans.list_for_user(user_id)

    async def list_for_project(self, user_id: str, project_id: str) -> List[Scan]:
        """Scans for an owned project, newest first; 404 for others' projects."""
        project = await self._projects.get(user_id, project_id)
        if project is None:
            raise ProjectNotFoundError("Project not found.")
        return await self._scans.list_for_project(user_id, project_id)

    async def get_for_user(self, user_id: str, scan_id: str) -> Scan:
        """Return ``scan_id`` if owned; 404 otherwise (no existence leak)."""
        scan = await self._scans.get(user_id, scan_id)
        if scan is None:
            raise ScanNotFoundError("Scan not found.")
        return scan

    async def get_issues_for_user(
        self,
        user_id: str,
        scan_id: str,
    ) -> List[StoredAccessibilityIssue]:
        """Return an owned scan's issues; 404 for missing/foreign scans."""
        scan = await self._scans.get(user_id, scan_id)
        if scan is None:
            raise ScanNotFoundError("Scan not found.")
        return await self._issues.list_for_scan(user_id, scan_id)

    async def delete_for_user(self, user_id: str, scan_id: str) -> None:
        """Delete an owned scan (cascades its issues); 404 otherwise."""
        deleted = await self._scans.delete(user_id, scan_id)
        if not deleted:
            raise ScanNotFoundError("Scan not found.")

    # --- internals ----------------------------------------------------------

    async def _mark_failed(self, user_id: str, scan_id: str, error: Exception) -> None:
        """Move a RUNNING scan to FAILED with a sanitized error message."""
        current = await self._scans.get(user_id, scan_id)
        if current is None or current.status != ScanStatus.RUNNING:
            return
        assert_valid_transition(current.status, ScanStatus.FAILED)
        await self._scans.update(
            user_id,
            scan_id,
            ScanUpdate(
                status=ScanStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                summary={"error": sanitize_failure_message(error)},
            ),
        )
