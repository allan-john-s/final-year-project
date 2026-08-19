"""Tests for the scan execution service.

The service drives the lifecycle through the repository protocols; these
tests inject in-memory fakes (faithful to the contracts, ownership-scoped)
plus a fake scanner selected via the factory, so the whole pipeline is
exercised deterministically — no network, no browser, no Supabase.

Covers: project ownership, PENDING → RUNNING, successful execution (issues
persisted, COMPLETED with counts/score/metadata), failure → FAILED with a
sanitized message, illegal transitions, and IDOR-safe reads/deletes.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import pytest

from app.projects.exceptions import ProjectNotFoundError
from app.projects.models import Project, ProjectCreate, ProjectStatus, ProjectUpdate
from app.scans.exceptions import (
    InvalidScanTransitionError,
    ScanConfigurationError,
    ScanExecutionError,
    ScanNotFoundError,
)
from app.scans.models import (
    Scan,
    ScanCreate,
    ScanStatus,
    ScanUpdate,
    StoredAccessibilityIssue,
    assert_valid_transition,
)
from app.scans.services import ScanExecutionService, sanitize_failure_message
from app.scanners.exceptions import ScannerRuntimeError
from app.scanners.factory import ScannerUnavailableError
from app.scanners.models import (
    AccessibilityIssue,
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScannerType,
    ScanTiming,
    WcagLevel,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


# --- fakes ----------------------------------------------------------------


class FakeProjectRepository:
    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}

    def seed(self, user_id: str, project_id: str = "") -> Project:
        project = Project(
            id=project_id or str(uuid4()),
            user_id=user_id,
            name="Seed",
            website_url="https://example.com",
            status=ProjectStatus.NOT_SCANNED,
            created_at=now(),
            updated_at=now(),
        )
        self._projects[project.id] = project
        return project

    async def create(self, data: ProjectCreate) -> Project:
        raise NotImplementedError

    async def list_by_user(self, user_id: str) -> List[Project]:
        raise NotImplementedError

    async def get(self, user_id: str, project_id: str) -> Optional[Project]:
        project = self._projects.get(project_id)
        if project is not None and project.user_id == user_id:
            return project
        return None

    async def update(self, user_id: str, project_id: str, changes: ProjectUpdate) -> Optional[Project]:
        raise NotImplementedError

    async def delete(self, user_id: str, project_id: str) -> bool:
        raise NotImplementedError


class FakeScanRepository:
    def __init__(self) -> None:
        self._scans: Dict[str, Scan] = {}
        self.creates: List[ScanCreate] = []
        self.updates: List[ScanUpdate] = []

    def seed(self, user_id: str, *, project_id: str = "project-1", status: ScanStatus = ScanStatus.COMPLETED) -> Scan:
        scan = Scan(
            id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            scanner_type=ScannerType.AXE,
            status=status,
            scan_url="https://example.com",
            created_at=now(),
        )
        self._scans[scan.id] = scan
        return scan

    async def create(self, data: ScanCreate) -> Scan:
        self.creates.append(data)
        scan = Scan(
            id=str(uuid4()),
            project_id=data.project_id,
            user_id=data.user_id,
            scanner_type=data.scanner_type,
            status=data.status,
            scan_url=data.scan_url,
            created_at=now(),
        )
        self._scans[scan.id] = scan
        return scan

    async def get(self, user_id: str, scan_id: str) -> Optional[Scan]:
        scan = self._scans.get(scan_id)
        if scan is not None and scan.user_id == user_id:
            return scan
        return None

    async def list_for_project(self, user_id: str, project_id: str) -> List[Scan]:
        owned = [s for s in self._scans.values() if s.user_id == user_id and s.project_id == project_id]
        return sorted(owned, key=lambda s: s.created_at, reverse=True)

    async def list_for_user(self, user_id: str) -> List[Scan]:
        owned = [s for s in self._scans.values() if s.user_id == user_id]
        return sorted(owned, key=lambda s: s.created_at, reverse=True)

    async def update(self, user_id: str, scan_id: str, changes: ScanUpdate) -> Optional[Scan]:
        self.updates.append(changes)
        scan = await self.get(user_id, scan_id)
        if scan is None:
            return None
        merged = scan.model_copy(update=changes.model_dump(exclude_none=True))
        self._scans[scan_id] = merged
        return merged

    async def delete(self, user_id: str, scan_id: str) -> bool:
        scan = self._scans.get(scan_id)
        if scan is None or scan.user_id != user_id:
            return False
        del self._scans[scan_id]
        return True


class FakeIssueRepository:
    def __init__(self) -> None:
        self._issues: Dict[str, List[StoredAccessibilityIssue]] = {}
        self.inserts: List[List[AccessibilityIssue]] = []

    async def insert_many(self, scan_id: str, issues: List[AccessibilityIssue]) -> int:
        self.inserts.append(issues)
        stored = [
            StoredAccessibilityIssue(
                id=str(uuid4()), scan_id=scan_id, created_at=now(), **issue.model_dump()
            )
            for issue in issues
        ]
        self._issues.setdefault(scan_id, []).extend(stored)
        return len(issues)

    async def list_for_scan(self, user_id: str, scan_id: str) -> List[StoredAccessibilityIssue]:
        return list(self._issues.get(scan_id, []))

    def issues_for(self, scan_id: str) -> List[StoredAccessibilityIssue]:
        return list(self._issues.get(scan_id, []))


class FakeScanner:
    """Deterministic scanner: returns a fixed result or raises, as configured."""

    name = "fake-scanner"
    version = "1.0.0"
    wcag_version = "2.2"
    scanner_type = ScannerType.AXE
    fail_with: Optional[Exception] = None

    async def scan(self, url: str, *, depth: int = 1) -> NormalizedScanResult:
        if self.fail_with is not None:
            raise self.fail_with
        metadata = ScanMetadata(
            scanner_name=self.name,
            scanner_type=self.scanner_type,
            scanner_version=self.version,
            wcag_version=self.wcag_version,
            scan_url=url,
            scan_depth=depth,
            pages_scanned=1,
            browser_name="chromium",
            browser_version="128.0.0.0",
            user_agent="fake",
            total_dom_elements=10,
            tested_elements=2,
        )
        return NormalizedScanResult(
            metadata=metadata,
            timing=ScanTiming(duration_ms=1500, normalization_duration_ms=25),
            issues=[
                AccessibilityIssue(
                    rule_id="color-contrast",
                    rule_name="Elements must have sufficient color contrast",
                    impact=Impact.SERIOUS,
                    wcag_level=WcagLevel.AA,
                    tags=["wcag2aa"],
                    element_selector="#main > p",
                    html_snippet="<p>text</p>",
                    failure_summary="Fix the contrast",
                ),
                AccessibilityIssue(rule_id="image-alt", rule_name="Images must have alt text", impact=Impact.MINOR),
            ],
        )


def run_async(coro):
    return asyncio.run(coro)


@pytest.fixture
def service(monkeypatch) -> tuple[ScanExecutionService, FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    """Service with a fake scanner returned by the (patched) factory."""
    scans = FakeScanRepository()
    issues = FakeIssueRepository()
    projects = FakeProjectRepository()
    svc = ScanExecutionService(scans=scans, issues=issues, projects=projects)

    def _get_scanner(scanner_type: ScannerType):
        return FakeScanner()

    monkeypatch.setattr("app.scans.services.get_scanner", _get_scanner)
    return svc, scans, issues, projects


# --- transition validation -------------------------------------------------


def test_transition_validation_accepts_only_legal_moves() -> None:
    assert_valid_transition(ScanStatus.PENDING, ScanStatus.RUNNING)
    assert_valid_transition(ScanStatus.RUNNING, ScanStatus.COMPLETED)
    assert_valid_transition(ScanStatus.RUNNING, ScanStatus.FAILED)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ScanStatus.PENDING, ScanStatus.COMPLETED),
        (ScanStatus.PENDING, ScanStatus.FAILED),
        (ScanStatus.COMPLETED, ScanStatus.RUNNING),
        (ScanStatus.FAILED, ScanStatus.RUNNING),
        (ScanStatus.COMPLETED, ScanStatus.FAILED),
        (ScanStatus.PENDING, ScanStatus.PENDING),
    ],
)
def test_transition_validation_rejects_illegal_moves(current, target) -> None:
    with pytest.raises(InvalidScanTransitionError):
        assert_valid_transition(current, target)


# --- start_scan -------------------------------------------------------------


def test_start_scan_creates_pending_then_running(service) -> None:
    svc, scans, _issues, projects = service
    project = projects.seed("user-a")

    result = run_async(svc.start_scan("user-a", project.id))

    assert result.status is ScanStatus.RUNNING
    assert result.project_id == project.id
    assert result.scan_url == "https://example.com"
    assert result.started_at is not None
    assert len(scans.creates) == 1
    assert scans.creates[0].status is ScanStatus.PENDING
    assert scans.creates[0].user_id == "user-a"
    assert scans.updates[-1].status is ScanStatus.RUNNING


def test_start_scan_requires_owned_project(service) -> None:
    svc, scans, _issues, projects = service
    project = projects.seed("user-b")

    with pytest.raises(ProjectNotFoundError):
        run_async(svc.start_scan("user-a", project.id))

    assert len(scans.creates) == 0  # nothing was created


def test_start_scan_missing_project_404(service) -> None:
    svc, scans, _issues, _projects = service
    with pytest.raises(ProjectNotFoundError):
        run_async(svc.start_scan("user-a", str(uuid4())))
    assert len(scans.creates) == 0


def test_start_scan_unregistered_scanner_is_configuration_error(service, monkeypatch) -> None:
    svc, scans, _issues, projects = service
    project = projects.seed("user-a")

    def _unavailable(scanner_type: ScannerType):
        raise ScannerUnavailableError(f"No scanner engine is registered for {scanner_type.value}.")

    monkeypatch.setattr("app.scans.services.get_scanner", _unavailable)

    with pytest.raises(ScanConfigurationError):
        run_async(svc.start_scan("user-a", project.id))
    assert len(scans.creates) == 0


# --- execute_scan: success ---------------------------------------------------


def test_execute_scan_completes_and_persists_everything(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = run_async(svc.start_scan("user-a", project.id))

    completed = run_async(svc.execute_scan("user-a", scan.id))

    assert completed.status is ScanStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.duration_ms == 1500
    assert completed.total_issues == 2
    assert completed.critical_count == 0
    assert completed.serious_count == 1
    assert completed.minor_count == 1
    assert completed.accessibility_score == 94.0  # 100 - 5 - 1
    assert completed.scanner_name == "fake-scanner"
    assert completed.scanner_version == "1.0.0"
    assert completed.wcag_version == "2.2"
    assert completed.scan_url == "https://example.com"
    assert completed.browser_name == "chromium"
    assert completed.tested_elements == 2
    assert completed.normalization_duration_ms == 25
    assert completed.persistence_duration_ms is not None
    assert completed.summary["total_issues"] == 2

    # Issues persisted for this scan.
    stored = issues.issues_for(scan.id)
    assert len(stored) == 2
    assert stored[0].scan_id == scan.id
    assert stored[0].impact is Impact.SERIOUS


def test_execute_scan_requires_running_state(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-a", status=ScanStatus.COMPLETED)

    with pytest.raises(InvalidScanTransitionError):
        run_async(svc.execute_scan("user-a", scan.id))


def test_execute_scan_missing_scan_404(service) -> None:
    svc, _scans, _issues, _projects = service
    with pytest.raises(ScanNotFoundError):
        run_async(svc.execute_scan("user-a", str(uuid4())))


def test_execute_scan_foreign_scan_404(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-b", status=ScanStatus.RUNNING)

    with pytest.raises(ScanNotFoundError):
        run_async(svc.execute_scan("user-a", scan.id))


# --- execute_scan: failure ---------------------------------------------------


def test_execute_scan_failure_marks_failed_and_raises(service, monkeypatch) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = run_async(svc.start_scan("user-a", project.id))

    class Boom(FakeScanner):
        fail_with = ScannerRuntimeError("Timed out loading the target")

    monkeypatch.setattr("app.scans.services.get_scanner", lambda t: Boom())

    with pytest.raises(ScanExecutionError) as excinfo:
        run_async(svc.execute_scan("user-a", scan.id))

    failed = run_async(svc.get_for_user("user-a", scan.id))
    assert failed.status is ScanStatus.FAILED
    assert failed.completed_at is not None
    assert failed.summary.get("error") == "Timed out loading the target"
    assert "Traceback" not in str(excinfo.value)
    assert issues.issues_for(scan.id) == []  # nothing persisted on failure


def test_execute_scan_failure_message_is_sanitized(service, monkeypatch) -> None:
    svc, scans, _issues, projects = service
    project = projects.seed("user-a")
    scan = run_async(svc.start_scan("user-a", project.id))

    class Boom(FakeScanner):
        fail_with = RuntimeError("  boom\n  line two\n  line three   ")

    monkeypatch.setattr("app.scans.services.get_scanner", lambda t: Boom())

    with pytest.raises(ScanExecutionError):
        run_async(svc.execute_scan("user-a", scan.id))

    failed = run_async(svc.get_for_user("user-a", scan.id))
    assert failed.summary.get("error") == "boom line two line three"


def test_sanitize_failure_message_truncates_and_defaults() -> None:
    long = "x" * 5000
    assert len(sanitize_failure_message(RuntimeError(long))) <= 2000
    assert sanitize_failure_message(RuntimeError("  ")) == "The scan failed for an unknown reason."


def test_run_scan_swallows_failures(service, monkeypatch) -> None:
    """The background wrapper never raises — the row records the failure."""
    svc, scans, _issues, projects = service
    project = projects.seed("user-a")
    scan = run_async(svc.start_scan("user-a", project.id))

    class Boom(FakeScanner):
        fail_with = ScannerRuntimeError("boom")

    monkeypatch.setattr("app.scans.services.get_scanner", lambda t: Boom())

    run_async(svc.run_scan("user-a", scan.id))  # must not raise

    failed = run_async(svc.get_for_user("user-a", scan.id))
    assert failed.status is ScanStatus.FAILED


# --- reads / deletes ----------------------------------------------------------


def test_list_for_user_returns_only_own(service) -> None:
    svc, scans, _issues, _projects = service
    scans.seed("user-a", project_id="p-a")
    scans.seed("user-b", project_id="p-b")

    mine = run_async(svc.list_for_user("user-a"))

    assert len(mine) == 1
    assert mine[0].user_id == "user-a"


def test_list_for_project_requires_owned_project(service) -> None:
    svc, _scans, _issues, projects = service
    theirs = projects.seed("user-b")

    with pytest.raises(ProjectNotFoundError):
        run_async(svc.list_for_project("user-a", theirs.id))


def test_get_foreign_scan_404(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-b")

    with pytest.raises(ScanNotFoundError):
        run_async(svc.get_for_user("user-a", scan.id))


def test_get_issues_requires_owned_scan(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-b")

    with pytest.raises(ScanNotFoundError):
        run_async(svc.get_issues_for_user("user-a", scan.id))


def test_get_issues_returns_persisted_issues(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = run_async(svc.start_scan("user-a", project.id))
    run_async(svc.execute_scan("user-a", scan.id))

    stored = run_async(svc.get_issues_for_user("user-a", scan.id))

    assert len(stored) == 2
    assert stored[0].id
    assert stored[0].created_at is not None


def test_delete_foreign_scan_404(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-b")

    with pytest.raises(ScanNotFoundError):
        run_async(svc.delete_for_user("user-a", scan.id))


def test_delete_own_scan_removes_it(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-a")

    run_async(svc.delete_for_user("user-a", scan.id))

    with pytest.raises(ScanNotFoundError):
        run_async(svc.get_for_user("user-a", scan.id))
