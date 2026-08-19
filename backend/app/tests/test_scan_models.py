"""Tests for scan domain models.

Covers the controlled status lifecycle, model validation, ownership fields
(user_id always required at creation), and the mapping helpers that persist a
normalized result. Pure domain tests — no network or credentials.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.scans.exceptions import InvalidScanTransitionError
from app.scans.models import (
    Scan,
    ScanCreate,
    ScanStatus,
    ScanUpdate,
    StoredAccessibilityIssue,
    assert_valid_transition,
)
from app.scanners.models import (
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScannerType,
    WcagLevel,
)
from app.tests.test_scanner_models import make_issue, make_metadata, make_result


def make_scan(**overrides) -> Scan:
    defaults = {
        "id": "scan-1",
        "project_id": "project-1",
        "user_id": "user-a",
        "scanner_type": ScannerType.AXE,
        "status": ScanStatus.PENDING,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Scan(**defaults)


def make_create(**overrides) -> ScanCreate:
    defaults = {
        "user_id": "user-a",
        "project_id": "project-1",
        "scanner_type": ScannerType.AXE,
    }
    defaults.update(overrides)
    return ScanCreate(**defaults)


# --- status lifecycle ------------------------------------------------------


def test_status_accepts_only_controlled_values() -> None:
    for status in (ScanStatus.PENDING, ScanStatus.RUNNING, ScanStatus.COMPLETED, ScanStatus.FAILED):
        assert make_scan(status=status).status is status


def test_status_rejects_arbitrary_values() -> None:
    with pytest.raises(ValidationError):
        make_scan(status="CANCELLED")
    with pytest.raises(ValidationError):
        make_scan(status="running")  # lowercase not allowed
    with pytest.raises(ValidationError):
        make_scan(status=123)


def test_status_rejects_cancelled_by_design() -> None:
    """CANCELLED is deliberately not modelled yet — it must not slip in."""
    assert not hasattr(ScanStatus, "CANCELLED")


def test_pending_is_the_default_lifecycle_start() -> None:
    assert make_create().status is ScanStatus.PENDING
    assert make_scan().status is ScanStatus.PENDING


# --- ownership --------------------------------------------------------------


def test_create_always_carries_owner_and_project() -> None:
    create = make_create()
    assert create.user_id == "user-a"
    assert create.project_id == "project-1"


def test_create_requires_owner_and_project() -> None:
    with pytest.raises(ValidationError):
        ScanCreate(scanner_type=ScannerType.AXE)  # no user_id / project_id
    with pytest.raises(ValidationError):
        ScanCreate(user_id="user-a", scanner_type=ScannerType.AXE)  # no project_id


def test_scan_requires_owner_and_project() -> None:
    with pytest.raises(ValidationError):
        Scan(
            id="s-1",
            scanner_type=ScannerType.AXE,
            created_at=datetime.now(timezone.utc),
        )


def test_create_rejects_invalid_scanner_type() -> None:
    with pytest.raises(ValidationError):
        make_create(scanner_type="GHOST")


# --- validation of stored fields -------------------------------------------


def test_scan_rejects_negative_counts() -> None:
    for field in ("total_issues", "critical_count", "serious_count", "moderate_count", "minor_count"):
        with pytest.raises(ValidationError):
            make_scan(**{field: -1})


def test_scan_rejects_negative_or_oob_score() -> None:
    with pytest.raises(ValidationError):
        make_scan(accessibility_score=-1)
    with pytest.raises(ValidationError):
        make_scan(accessibility_score=101)
    assert make_scan(accessibility_score=87.5).accessibility_score == 87.5


def test_update_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        ScanUpdate(status="CANCELLED")
    assert ScanUpdate(status=ScanStatus.RUNNING).status is ScanStatus.RUNNING


def test_update_allows_partial_lifecycle_changes() -> None:
    update = ScanUpdate(status=ScanStatus.COMPLETED, duration_ms=1500)
    assert update.status is ScanStatus.COMPLETED
    assert update.duration_ms == 1500
    assert update.total_issues is None  # untouched


# --- normalized result → persistence mapping --------------------------------


def test_create_with_result_attaches_metadata_and_counts() -> None:
    result = NormalizedScanResult(
        metadata=ScanMetadata(
            scanner_name="axe-core",
            scanner_type=ScannerType.AXE,
            scanner_version="4.10.2",
            wcag_version="2.2",
            scan_url="https://example.com",
            scan_depth=1,
            pages_scanned=1,
            browser_name="chromium",
        ),
        issues=[
            make_issue(impact=Impact.CRITICAL),
            make_issue(impact=Impact.MINOR),
        ],
    )

    resolved = make_create().with_result(result)

    assert resolved.status is ScanStatus.COMPLETED
    assert resolved.scanner_name == "axe-core"
    assert resolved.scan_url == "https://example.com"
    assert resolved.total_issues == 2
    assert resolved.critical_count == 1
    assert resolved.minor_count == 1
    assert resolved.summary == {
        "total_issues": 2,
        "critical_count": 1,
        "serious_count": 0,
        "moderate_count": 0,
        "minor_count": 1,
    }


def test_update_from_result_carries_lifecycle_completion() -> None:
    update = ScanUpdate().from_result(make_result())

    assert update.status is ScanStatus.COMPLETED
    assert update.total_issues == 1
    assert update.scanner_name == "axe-core"
    assert update.normalization_duration_ms == 40
    assert update.duration_ms == 1200
    assert update.wcag_version == "2.2"


def test_from_result_never_reassigns_ownership() -> None:
    """Result-derived updates contain no user/project fields — ownership stays
    wherever the repository scopes it."""
    update = ScanUpdate().from_result(make_result())
    dumped = update.model_dump()
    assert "user_id" not in dumped
    assert "project_id" not in dumped


# --- lifecycle transitions ---------------------------------------------------


def test_legal_transitions_are_accepted() -> None:
    assert_valid_transition(ScanStatus.PENDING, ScanStatus.RUNNING)
    assert_valid_transition(ScanStatus.RUNNING, ScanStatus.COMPLETED)
    assert_valid_transition(ScanStatus.RUNNING, ScanStatus.FAILED)


def test_illegal_transitions_are_rejected() -> None:
    for current, target in (
        (ScanStatus.PENDING, ScanStatus.COMPLETED),
        (ScanStatus.PENDING, ScanStatus.FAILED),
        (ScanStatus.COMPLETED, ScanStatus.RUNNING),
        (ScanStatus.FAILED, ScanStatus.RUNNING),
        (ScanStatus.COMPLETED, ScanStatus.FAILED),
        (ScanStatus.PENDING, ScanStatus.PENDING),
    ):
        with pytest.raises(InvalidScanTransitionError):
            assert_valid_transition(current, target)


# --- stored issue model ------------------------------------------------------


def test_stored_issue_adds_row_identity() -> None:
    issue = StoredAccessibilityIssue(
        id="issue-1",
        scan_id="scan-1",
        created_at=datetime.now(timezone.utc),
        **make_issue().model_dump(),
    )
    assert issue.rule_id == "color-contrast"
    assert issue.impact is Impact.SERIOUS
    assert issue.scan_id == "scan-1"


def test_stored_issue_requires_row_identity() -> None:
    with pytest.raises(ValidationError):
        StoredAccessibilityIssue(**make_issue().model_dump())  # no id/scan_id/created_at


def test_stored_issue_round_trips_through_json() -> None:
    issue = StoredAccessibilityIssue(
        id="issue-1",
        scan_id="scan-1",
        created_at=datetime.now(timezone.utc),
        **make_issue().model_dump(),
    )
    restored = StoredAccessibilityIssue.model_validate_json(issue.model_dump_json())
    assert restored.id == "issue-1"
    assert restored.scan_id == "scan-1"
    assert restored.impact is Impact.SERIOUS
    assert restored.tags == ["wcag2aa", "wcag143"]
