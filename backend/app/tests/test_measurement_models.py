"""Tests for measurement domain models and classification (Module 8).

Covers: model validation, fingerprint generation, severity burden calculation,
improvement classification rules, and deterministic behavior.
"""

import pytest

from app.measurements.models import (
    ImprovementMeasurement,
    IssueFingerprint,
    MEASUREMENT_VERSION,
    MeasurementStatus,
    SeverityBurden,
)
from app.measurements.services import (
    SEVERITY_WEIGHTS,
    build_measurement_summary,
    classify_measurement,
)


# --- IssueFingerprint --------------------------------------------------------


class TestIssueFingerprint:
    def test_from_issue_data_deterministic(self) -> None:
        fp1 = IssueFingerprint.from_issue_data("color-contrast", "#main > p", "html/body/main/p", "SERIOUS")
        fp2 = IssueFingerprint.from_issue_data("color-contrast", "#main > p", "html/body/main/p", "SERIOUS")
        assert fp1.fingerprint == fp2.fingerprint

    def test_different_issues_different_fingerprints(self) -> None:
        fp1 = IssueFingerprint.from_issue_data("color-contrast", "#main > p", "", "SERIOUS")
        fp2 = IssueFingerprint.from_issue_data("image-alt", "#main > img", "", "MINOR")
        assert fp1.fingerprint != fp2.fingerprint

    def test_different_selectors_different_fingerprints(self) -> None:
        fp1 = IssueFingerprint.from_issue_data("color-contrast", "#main > p", "", "SERIOUS")
        fp2 = IssueFingerprint.from_issue_data("color-contrast", "#sidebar > p", "", "SERIOUS")
        assert fp1.fingerprint != fp2.fingerprint

    def test_fingerprint_fields_populated(self) -> None:
        fp = IssueFingerprint.from_issue_data("color-contrast", "#main", "html/body", "CRITICAL")
        assert fp.rule_id == "color-contrast"
        assert fp.selector == "#main"
        assert fp.dom_path == "html/body"
        assert fp.impact == "CRITICAL"
        assert len(fp.fingerprint) == 32  # SHA-256 truncated to 32 hex chars


# --- SeverityBurden ----------------------------------------------------------


class TestSeverityBurden:
    def test_total_burden_calculation(self) -> None:
        burden = SeverityBurden(critical=2, serious=3, moderate=4, minor=5)
        expected = 2 * 10 + 3 * 5 + 4 * 2 + 5 * 1  # 20 + 15 + 8 + 5 = 48
        assert burden.total_burden == expected

    def test_total_issues(self) -> None:
        burden = SeverityBurden(critical=1, serious=2, moderate=3, minor=4)
        assert burden.total_issues == 10

    def test_zero_burden(self) -> None:
        burden = SeverityBurden(critical=0, serious=0, moderate=0, minor=0)
        assert burden.total_burden == 0
        assert burden.total_issues == 0


# --- Severity weights consistency -------------------------------------------


class TestSeverityWeights:
    def test_weights_match_accessibility_score_penalties(self) -> None:
        """Ensure SEVERITY_WEIGHTS match the score penalty weights from scanner models."""
        assert SEVERITY_WEIGHTS["CRITICAL"] == 10
        assert SEVERITY_WEIGHTS["SERIOUS"] == 5
        assert SEVERITY_WEIGHTS["MODERATE"] == 2
        assert SEVERITY_WEIGHTS["MINOR"] == 1


# --- classify_measurement ----------------------------------------------------


class TestClassifyMeasurement:
    def test_improved_score_increased(self) -> None:
        status = classify_measurement(
            score_delta=5.0,
            severity_before=SeverityBurden(critical=2, serious=3, moderate=4, minor=5),
            severity_after=SeverityBurden(critical=1, serious=2, moderate=3, minor=4),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.IMPROVED

    def test_improved_score_increased_same_severity(self) -> None:
        status = classify_measurement(
            score_delta=2.0,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.IMPROVED

    def test_no_change_within_threshold(self) -> None:
        status = classify_measurement(
            score_delta=0.0,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.NO_CHANGE

    def test_no_change_small_positive(self) -> None:
        status = classify_measurement(
            score_delta=0.3,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.NO_CHANGE

    def test_regressed_score_decreased(self) -> None:
        status = classify_measurement(
            score_delta=-5.0,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=2, serious=2, moderate=2, minor=2),
            new_severe_count=2,
        )
        assert status == MeasurementStatus.REGRESSED

    def test_regressed_new_severe_issues(self) -> None:
        status = classify_measurement(
            score_delta=-1.0,
            severity_before=SeverityBurden(critical=1, serious=0, moderate=0, minor=0),
            severity_after=SeverityBurden(critical=1, serious=2, moderate=0, minor=0),
            new_severe_count=2,
        )
        assert status == MeasurementStatus.REGRESSED

    def test_completed_no_scores(self) -> None:
        status = classify_measurement(
            score_delta=None,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.COMPLETED

    def test_improved_reduced_severity(self) -> None:
        status = classify_measurement(
            score_delta=0.0,
            severity_before=SeverityBurden(critical=2, serious=3, moderate=4, minor=5),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=2, minor=3),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.IMPROVED

    def test_boundary_threshold_positive(self) -> None:
        """Exactly at threshold should be NO_CHANGE (not > threshold)."""
        status = classify_measurement(
            score_delta=0.5,
            severity_before=SeverityBurden(critical=0, serious=0, moderate=0, minor=0),
            severity_after=SeverityBurden(critical=0, serious=0, moderate=0, minor=0),
            new_severe_count=0,
        )
        assert status == MeasurementStatus.NO_CHANGE


# --- build_measurement_summary -----------------------------------------------


class TestBuildSummary:
    def test_improved_summary(self) -> None:
        summary = build_measurement_summary(
            status=MeasurementStatus.IMPROVED,
            score_delta=10.0,
            improvement_pct=10.0,
            issues_resolved=3,
            issues_remaining=5,
            new_issues=0,
            severity_before=SeverityBurden(critical=1, serious=2, moderate=3, minor=4),
            severity_after=SeverityBurden(critical=0, serious=1, moderate=2, minor=3),
        )
        assert "improved" in summary.lower()
        assert "resolved" in summary.lower()
        assert "10.0%" in summary

    def test_no_change_summary(self) -> None:
        summary = build_measurement_summary(
            status=MeasurementStatus.NO_CHANGE,
            score_delta=0.0,
            improvement_pct=0.0,
            issues_resolved=0,
            issues_remaining=10,
            new_issues=0,
            severity_before=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
            severity_after=SeverityBurden(critical=1, serious=1, moderate=1, minor=1),
        )
        assert "no meaningful change" in summary.lower()

    def test_regressed_summary(self) -> None:
        summary = build_measurement_summary(
            status=MeasurementStatus.REGRESSED,
            score_delta=-5.0,
            improvement_pct=-5.0,
            issues_resolved=0,
            issues_remaining=10,
            new_issues=3,
            severity_before=SeverityBurden(critical=0, serious=0, moderate=0, minor=0),
            severity_after=SeverityBurden(critical=2, serious=1, moderate=0, minor=0),
        )
        assert "regressed" in summary.lower()


# --- ImprovementMeasurement model validation --------------------------------


class TestImprovementMeasurement:
    def test_valid_measurement(self) -> None:
        m = ImprovementMeasurement(
            id="m-test-1",
            remediation_id="r-1",
            original_scan_id="scan-orig",
            followup_scan_id="scan-fup",
            original_accessibility_score=80.0,
            followup_accessibility_score=90.0,
            score_delta=10.0,
            score_improvement_percentage=12.5,
            original_issue_count=10,
            followup_issue_count=5,
            issues_resolved=5,
            issues_remaining=5,
            new_issues_introduced=0,
            critical_before=2,
            critical_after=0,
            serious_before=3,
            serious_after=1,
            moderate_before=3,
            moderate_after=2,
            minor_before=2,
            minor_after=2,
            status=MeasurementStatus.IMPROVED,
            measurement_summary="Accessibility improved.",
        )
        assert m.id == "m-test-1"
        assert m.status == MeasurementStatus.IMPROVED
        assert m.score_delta == 10.0
        assert m.measurement_version == MEASUREMENT_VERSION

    def test_none_scores_valid(self) -> None:
        """Measurements can have None scores if the scan didn't compute them."""
        m = ImprovementMeasurement(
            id="m-test-2",
            remediation_id="r-1",
            original_scan_id="scan-orig",
            followup_scan_id="scan-fup",
            original_accessibility_score=None,
            followup_accessibility_score=None,
            score_delta=None,
            score_improvement_percentage=None,
            original_issue_count=10,
            followup_issue_count=8,
            issues_resolved=2,
            issues_remaining=8,
            new_issues_introduced=0,
            critical_before=1,
            critical_after=1,
            serious_before=2,
            serious_after=2,
            moderate_before=3,
            moderate_after=3,
            minor_before=4,
            minor_after=2,
            status=MeasurementStatus.COMPLETED,
            measurement_summary="Measurement completed.",
        )
        assert m.original_accessibility_score is None
        assert m.followup_accessibility_score is None
