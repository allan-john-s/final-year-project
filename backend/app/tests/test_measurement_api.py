"""Tests for the measurement API surface (Module 8).

Covers: authentication, measurement creation, retrieval, ownership validation,
and error responses.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.measurements import get_measurement_service
from app.measurements.models import MeasurementStatus
from app.measurements.services import MeasurementService
from app.measurements.store import InMemoryMeasurementStore, get_measurement_store
from app.main import create_app
from app.remediations.models import RemediationProposal, RemediationStatus, ProposedChange
from app.remediations.store import RemediationStore, get_remediation_store
from app.scans.models import Scan, ScanStatus
from typing import Optional
from app.scanners.models import ScannerType


USER_A = AuthUser(id="user-a", email="a@example.com", email_verified=True)
USER_B = AuthUser(id="user-b", email="b@example.com", email_verified=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_scan(
    *,
    scan_id: str,
    user_id: str = "user-a",
    status: ScanStatus = ScanStatus.COMPLETED,
    accessibility_score: float = 80.0,
    total_issues: int = 10,
    critical_count: int = 1,
    serious_count: int = 2,
    moderate_count: int = 3,
    minor_count: int = 4,
    created_at: Optional[datetime] = None,
) -> Scan:
    return Scan(
        id=scan_id,
        project_id="project-1",
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
            explanation="Added aria-label",
        ),
        expected_improvement="Button becomes accessible",
        validation_steps=["Test with screen reader"],
        provider="mock",
        confidence=0.8,
        status=status,
    )


def run(coro):
    return asyncio.run(coro)


class FakeScanAccessor:
    def __init__(self, scans: dict[str, Scan]) -> None:
        self._scans = scans

    async def get_scan(self, user_id: str, scan_id: str):
        scan = self._scans.get(scan_id)
        if scan and scan.user_id == user_id:
            return scan
        return None


def _build_service(scans, proposals, measurement_store=None):
    accessor = FakeScanAccessor(scans)
    rem_store = _FakeRemStore(proposals)
    m_store = measurement_store or InMemoryMeasurementStore()
    return MeasurementService(scan_accessor=accessor, remediation_store=rem_store, measurement_store=m_store)


class _FakeRemStore(RemediationStore):
    def __init__(self, proposals):
        self._proposals = proposals
    def get(self, pid):
        return self._proposals.get(pid)
    def list_for_scan(self, scan_id, user_id):
        return [p for p in self._proposals.values() if p.scan_id == scan_id]
    def save(self, p):
        self._proposals[p.id] = p
        return p
    def update_status(self, pid, status):
        p = self._proposals[pid]
        updated = p.model_copy(update={"status": status, "updated_at": _now()})
        self._proposals[pid] = updated
        return updated


def _client(scans, proposals, user=USER_A, measurement_store=None):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    m_store = measurement_store or InMemoryMeasurementStore()
    service = _build_service(scans, proposals, m_store)
    app.dependency_overrides[get_measurement_service] = lambda: service
    app.dependency_overrides[get_measurement_store] = lambda: m_store
    return TestClient(app)


# --- Authentication -----------------------------------------------------------


def test_measure_requires_authentication():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})
    client.app.dependency_overrides[get_current_user] = get_current_user

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    assert resp.status_code == 401


# --- Success ------------------------------------------------------------------


def test_create_measurement_success():
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
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "IMPROVED"
    assert body["original_accessibility_score"] == 60.0
    assert body["followup_accessibility_score"] == 80.0
    assert body["score_delta"] == 20.0
    assert body["original_scan_id"] == "scan-orig"
    assert body["followup_scan_id"] == "scan-fup"
    assert body["measurement_summary"]
    assert "resolved" in body["measurement_summary"].lower()


def test_list_measurements_for_remediation():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=2))
    followup1 = _make_scan(scan_id="scan-fup-1", created_at=_now() - timedelta(hours=1))
    followup2 = _make_scan(scan_id="scan-fup-2", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    m_store = InMemoryMeasurementStore()
    client = _client(
        {"scan-orig": original, "scan-fup-1": followup1, "scan-fup-2": followup2},
        {"r-1": proposal},
        measurement_store=m_store,
    )

    # Create two measurements
    client.post("/api/v1/remediations/r-1/measure", json={"followup_scan_id": "scan-fup-1"})
    client.post("/api/v1/remediations/r-1/measure", json={"followup_scan_id": "scan-fup-2"})

    resp = client.get("/api/v1/remediations/r-1/measurements")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2


# --- Error cases --------------------------------------------------------------


def test_measure_missing_remediation_404():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    client = _client({"scan-orig": original, "scan-fup": followup}, {})

    resp = client.post(
        "/api/v1/remediations/r-nonexistent/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    assert resp.status_code == 409


def test_measure_proposed_status_409():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig", status=RemediationStatus.PROPOSED)
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "measurement_remediation_invalid"


def test_measure_missing_followup_404():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original}, {"r-1": proposal})

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-nonexistent"},
    )
    assert resp.status_code == 404


def test_measure_incomplete_followup_409():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", status=ScanStatus.RUNNING, created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "measurement_scan_incomplete"


def test_measure_scan_order_invalid_409():
    original = _make_scan(scan_id="scan-orig", created_at=_now())
    followup = _make_scan(scan_id="scan-fup", created_at=_now() - timedelta(hours=1))
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "measurement_scan_order_invalid"


def test_measure_duplicate_409():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    client.post("/api/v1/remediations/r-1/measure", json={"followup_scan_id": "scan-fup"})
    resp = client.post("/api/v1/remediations/r-1/measure", json={"followup_scan_id": "scan-fup"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "measurement_duplicate"


def test_measure_missing_fields_422():
    client = _client({}, {})
    resp = client.post("/api/v1/remediations/r-1/measure", json={})
    assert resp.status_code == 422


def test_get_measurement_by_id():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    m_store = InMemoryMeasurementStore()
    client = _client(
        {"scan-orig": original, "scan-fup": followup},
        {"r-1": proposal},
        measurement_store=m_store,
    )

    gen_resp = client.post("/api/v1/remediations/r-1/measure", json={"followup_scan_id": "scan-fup"})
    assert gen_resp.status_code == 200
    measurement_id = gen_resp.json()["id"]

    get_resp = client.get(f"/api/v1/measurements/{measurement_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == measurement_id


def test_get_nonexistent_measurement_404():
    client = _client({}, {})
    resp = client.get("/api/v1/measurements/nonexistent")
    assert resp.status_code == 404


def test_response_has_no_secrets():
    original = _make_scan(scan_id="scan-orig", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")
    client = _client({"scan-orig": original, "scan-fup": followup}, {"r-1": proposal})

    body = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    ).json()

    serialized = str(body).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_foreign_user_measurement():
    """User B cannot measure a remediation created by User A."""
    original = _make_scan(scan_id="scan-orig", user_id="user-a", created_at=_now() - timedelta(hours=1))
    followup = _make_scan(scan_id="scan-fup", user_id="user-a", created_at=_now())
    proposal = _make_proposal(scan_id="scan-orig")

    client = _client(
        {"scan-orig": original, "scan-fup": followup},
        {"r-1": proposal},
        user=USER_B,
    )

    resp = client.post(
        "/api/v1/remediations/r-1/measure",
        json={"followup_scan_id": "scan-fup"},
    )
    # User B cannot see User A's follow-up scan
    assert resp.status_code == 404
