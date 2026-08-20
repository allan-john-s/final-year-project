"""Tests for the measurement service (Module 8).

Covers: measurement creation, scan comparison, ownership validation,
scan ordering, duplicate prevention, status transitions, and error paths.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from app.measurements.exceptions import (
    MeasurementDuplicateError,
    MeasurementRemediationError,
    MeasurementScanError,
    MeasurementScanIncompleteError,
    MeasurementScanOrderError,
)
from app.measurements.interfaces import MeasurementStore, ScanAccessor
from app.measurements.models import ImprovementMeasurement, MeasurementStatus
from app.measurements.services import MeasurementService
from app.measurements.store import InMemoryMeasurementStore
from app.remediations.models import RemediationProposal, RemediationStatus, ProposedChange
from app.remediations.store import RemediationStore
from app.scans.models import Scan, ScanStatus
from app.scanners.models import ScannerType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_scan(
    *,
    scan_id: str,
    user_id: str = "user-a",
    project_id: str = "project-1",
    status: ScanStatus = ScanStatus.COMPLETED,
    accessibility_score: Optional[float] = 80.0,
    total_issues: int = 10,
    critical_count: int = 1,
    serious_count: int = 2,
    moderate_count: int = 3,
    minor_count: int = 4,
    created_at: Optional[datetime] = None,
) -> Scan:
    return Scan(
        id=scan_id,
        project_id=project_id,
        user_id=user_id,
        scanner_type=ScannerType.AXE,
        status=status,
        accessibility_score=accessibility_score,
        total_issues=total_issues,
        critical_count=critical_count,
        serious_count=serious_count,
        moderate_count=moderate_count,
        minor_count=minor_count,
        created_at=created_at or _now(),
    )


def _make_proposal(
    *,
    proposal_id: str = "r-1",
    scan_id: str = "scan-orig",
    user_id: str = "user-a",
    status: RemediationStatus = RemediationStatus.ACCEPTED,
) -> RemediationProposal:
    return RemediationProposal(
        id=proposal_id,
        scan_id=scan_id,
        issue_id="issue-1",
        strategy_id="s-1",
        rank=1,
        title="Add aria-label",
        summary="Add aria-label to button",
        rationale="Button lacks accessible name",
        implementation_steps=["Add aria-label attribute"],
        proposed_change=ProposedChange(
            before="<button>Submit</button>",
            after='<button aria-label="Submit form">Submit</button>',
            explanation="Added aria-label for screen readers",
        ),
        expected_improvement="Button becomes accessible",
        validation_steps=["Test with screen reader"],
        provider="mock",
        confidence=0.8,
        status=status,
    )


class FakeScanAccessor(ScanAccessor):
    def __init__(self, scans: dict[str, Scan]) -> None:
        self._scans = scans

    async def get_scan(self, user_id: str, scan_id: str) -> Optional[Scan]:
        scan = self._scans.get(scan_id)
        if scan and scan.user_id == user_id:
            return scan
        return None


class FakeRemediationStore(RemediationStore):
    def __init__(self, proposals: dict[str, RemediationProposal]) -> None:
        self._proposals = proposals

    def get(self, proposal_id: str) -> Optional[RemediationProposal]:
        return self._proposals.get(proposal_id)

    def list_for_scan(self, scan_id: str, user_id: str):
        return [p for p in self._proposals.values() if p.scan_id == scan_id]


def run(coro):
    return asyncio.run(coro)


def _make_service(scans, proposals=None):
    proposals = proposals or {}
    scan_accessor = FakeScanAccessor(scans)
    remediation_store = FakeRemediationStore(proposals)
    measurement_store = InMemoryMeasurementStore()
    return MeasurementService(
        scan_accessor=scan_accessor,
        remediation_store=remediation_store,
        measurement_store=measurement_store,
    ), measurement_store


# --- Success cases -----------------------------------------------------------


class TestMeasureSuccess:
    def test_improved_measurement(self) -> None:
        original = _make_scan(
            scan_id="scan-orig",
            accessibility_score=60.0,
            total_issues=20,
            critical_count=3,
            serious_count=5,
            moderate_count=7,
            minor_count=5,
            created_at=_now() - timedelta(hours=1),
        )
        followup = _make_scan(
            scan_id="scan-fup",
            accessibility_score=80.0,
            total_issues=10,
            critical_count=1,
            serious_count=2,
            moderate_count=3,
            minor_count=4,
            created_at=_now(),
        )
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))

        assert m.status == MeasurementStatus.IMPROVED
        assert m.original_accessibility_score == 60.0
        assert m.followup_accessibility_score == 80.0
        assert m.score_delta == 20.0
        assert m.score_improvement_percentage == pytest.approx(33.33, abs=0.01)
        assert m.issues_resolved == 10
        assert m.new_issues_introduced == 0
        assert m.critical_before == 3
        assert m.critical_after == 1
        assert m.serious_before == 5
        assert m.serious_after == 2

    def test_regressed_measurement(self) -> None:
        original = _make_scan(
            scan_id="scan-orig",
            accessibility_score=90.0,
            total_issues=5,
            critical_count=0,
            serious_count=1,
            moderate_count=2,
            minor_count=2,
            created_at=_now() - timedelta(hours=1),
        )
        followup = _make_scan(
            scan_id="scan-fup",
            accessibility_score=70.0,
            total_issues=15,
            critical_count=3,
            serious_count=4,
            moderate_count=5,
            minor_count=3,
            created_at=_now(),
        )
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))

        assert m.status == MeasurementStatus.REGRESSED
        assert m.score_delta == -20.0
        assert m.new_issues_introduced == 10
        assert m.critical_after == 3

    def test_no_change_measurement(self) -> None:
        original = _make_scan(
            scan_id="scan-orig",
            accessibility_score=80.0,
            total_issues=10,
            critical_count=1,
            serious_count=2,
            moderate_count=3,
            minor_count=4,
            created_at=_now() - timedelta(hours=1),
        )
        followup = _make_scan(
            scan_id="scan-fup",
            accessibility_score=80.0,
            total_issues=10,
            critical_count=1,
            serious_count=2,
            moderate_count=3,
            minor_count=4,
            created_at=_now(),
        )
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))

        assert m.status == MeasurementStatus.NO_CHANGE
        assert m.score_delta == 0.0
        assert m.issues_resolved == 0
        assert m.new_issues_introduced == 0

    def test_measurement_persisted(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))

        retrieved = store.get(m.id)
        assert retrieved is not None
        assert retrieved.id == m.id

    def test_applied_status_also_works(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.APPLIED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))
        assert m.status in (MeasurementStatus.IMPROVED, MeasurementStatus.NO_CHANGE, MeasurementStatus.REGRESSED, MeasurementStatus.COMPLETED)


# --- Error cases --------------------------------------------------------------


class TestMeasureErrors:
    def test_missing_remediation(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {},
        )

        with pytest.raises(MeasurementRemediationError, match="not found"):
            run(service.measure("user-a", "r-nonexistent", "scan-fup"))

    def test_proposed_status_rejected(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.PROPOSED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementRemediationError, match="ACCEPTED or APPLIED"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_reviewed_status_rejected(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.REVIEWED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementRemediationError, match="ACCEPTED or APPLIED"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_rejected_status_rejected(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.REJECTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementRemediationError, match="ACCEPTED or APPLIED"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_missing_followup_scan(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementScanError, match="follow-up scan"):
            run(service.measure("user-a", "r-1", "scan-nonexistent"))

    def test_foreign_followup_scan(self) -> None:
        original = _make_scan(scan_id="scan-orig", user_id="user-a", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", user_id="user-b", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementScanError, match="follow-up scan"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_incomplete_followup_scan(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", status=ScanStatus.RUNNING, created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementScanIncompleteError, match="not completed"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_scan_order_invalid(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now())
        followup = _make_scan(scan_id="scan-fup", created_at=_now() - timedelta(hours=1))
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementScanOrderError, match="after the original"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_duplicate_measurement(self) -> None:
        original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        # First measurement succeeds
        run(service.measure("user-a", "r-1", "scan-fup"))

        # Second measurement for same pair is a duplicate
        with pytest.raises(MeasurementDuplicateError, match="already exists"):
            run(service.measure("user-a", "r-1", "scan-fup"))

    def test_original_scan_not_found(self) -> None:
        followup = _make_scan(scan_id="scan-fup", created_at=_now())
        proposal = _make_proposal(scan_id="scan-missing", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-fup": followup},
            {"r-1": proposal},
        )

        with pytest.raises(MeasurementScanError, match="original scan"):
            run(service.measure("user-a", "r-1", "scan-fup"))


# --- Score edge cases ---------------------------------------------------------


class TestScoreEdgeCases:
    def test_zero_original_score(self) -> None:
        original = _make_scan(
            scan_id="scan-orig",
            accessibility_score=0.0,
            total_issues=30,
            created_at=_now() - timedelta(hours=1),
        )
        followup = _make_scan(
            scan_id="scan-fup",
            accessibility_score=20.0,
            total_issues=10,
            created_at=_now(),
        )
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))
        assert m.score_improvement_percentage == 100.0  # Special case: 0 → positive

    def test_none_scores(self) -> None:
        original = _make_scan(
            scan_id="scan-orig",
            accessibility_score=None,
            total_issues=10,
            created_at=_now() - timedelta(hours=1),
        )
        followup = _make_scan(
            scan_id="scan-fup",
            accessibility_score=None,
            total_issues=5,
            created_at=_now(),
        )
        proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.ACCEPTED)
        service, store = _make_service(
            {"scan-orig": original, "scan-fup": followup},
            {"r-1": proposal},
        )

        m = run(service.measure("user-a", "r-1", "scan-fup"))
        assert m.score_delta is None
        assert m.score_improvement_percentage is None
        assert m.status == MeasurementStatus.COMPLETED
