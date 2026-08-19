"""Tests for the normalized scanner domain models.

Pure domain validation — no network, no Supabase credentials. Covers model
validation, controlled severity/level enums, serialization round-trips, and
summary-count derivation.
"""

import json

import pytest
from pydantic import ValidationError

from app.scanners.models import (
    AccessibilityIssue,
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScanTiming,
    ScannerType,
    WcagLevel,
    summarize_issues,
)


def make_metadata(**overrides) -> ScanMetadata:
    defaults = {
        "scanner_name": "axe-core",
        "scanner_type": ScannerType.AXE,
        "scanner_version": "4.10.2",
        "wcag_version": "2.2",
        "scan_url": "https://example.com",
        "scan_depth": 1,
        "pages_scanned": 1,
        "browser_name": "chromium",
        "browser_version": "126.0",
        "user_agent": "E2E test agent",
        "total_dom_elements": 120,
        "tested_elements": 84,
    }
    defaults.update(overrides)
    return ScanMetadata(**defaults)


def make_issue(**overrides) -> AccessibilityIssue:
    defaults = {
        "rule_id": "color-contrast",
        "rule_name": "Elements must have sufficient color contrast",
        "description": "Element has insufficient contrast",
        "help": "Color contrast",
        "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        "impact": Impact.SERIOUS,
        "wcag_level": WcagLevel.AA,
        "tags": ["wcag2aa", "wcag143"],
        "element_selector": "#main > p",
        "html_snippet": "<p>Low contrast text</p>",
        "failure_summary": "Fixed with #444 on #fff",
        "xpath": "/html/body/main/p[1]",
        "css_path": "main > p",
        "dom_path": "html > body > main > p",
        "screenshot_path": "scans/s-1/color-contrast.png",
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


def make_result(**overrides) -> NormalizedScanResult:
    defaults = {
        "metadata": make_metadata(),
        "timing": ScanTiming(duration_ms=1200, normalization_duration_ms=40),
        "issues": [make_issue()],
    }
    defaults.update(overrides)
    return NormalizedScanResult(**defaults)


# --- metadata --------------------------------------------------------------


def test_metadata_requires_scanner_identity() -> None:
    with pytest.raises(ValidationError):
        make_metadata(scanner_name="")
    with pytest.raises(ValidationError):
        make_metadata(scanner_version="")
    with pytest.raises(ValidationError):
        make_metadata(wcag_version="")


def test_metadata_validates_scan_url() -> None:
    with pytest.raises(ValidationError):
        make_metadata(scan_url="")
    with pytest.raises(ValidationError):
        make_metadata(scan_url="ftp://example.com")
    with pytest.raises(ValidationError):
        make_metadata(scan_url="https://exa mple.com")
    # Trimmed and accepted:
    assert make_metadata(scan_url="  https://example.com  ").scan_url == "https://example.com"


def test_metadata_rejects_invalid_scanner_type() -> None:
    with pytest.raises(ValidationError):
        make_metadata(scanner_type="GHOST")
    with pytest.raises(ValidationError):
        make_metadata(scanner_type=123)


def test_metadata_rejects_negative_counts_and_depth() -> None:
    with pytest.raises(ValidationError):
        make_metadata(total_dom_elements=-1)
    with pytest.raises(ValidationError):
        make_metadata(tested_elements=-1)
    with pytest.raises(ValidationError):
        make_metadata(scan_depth=0)


# --- issues ----------------------------------------------------------------


def test_issue_requires_rule_identity() -> None:
    with pytest.raises(ValidationError):
        make_issue(rule_id="")
    with pytest.raises(ValidationError):
        make_issue(rule_name="")


def test_issue_rejects_invalid_impact() -> None:
    with pytest.raises(ValidationError):
        make_issue(impact="HIGH")
    with pytest.raises(ValidationError):
        make_issue(impact="minor")  # lowercase not allowed — controlled enum


def test_issue_rejects_invalid_wcag_level() -> None:
    with pytest.raises(ValidationError):
        make_issue(wcag_level="B")
    with pytest.raises(ValidationError):
        make_issue(wcag_level="AA+")
    # None is allowed (some scanners do not map rules to WCAG levels).
    assert make_issue(wcag_level=None).wcag_level is None


def test_issue_rejects_empty_tags() -> None:
    with pytest.raises(ValidationError):
        make_issue(tags=["wcag2aa", "", "wcag143"])


def test_issue_defaults_are_safe() -> None:
    issue = AccessibilityIssue(rule_id="x", rule_name="y", impact=Impact.MINOR)
    assert issue.description == ""
    assert issue.tags == []
    assert issue.screenshot_path == ""


# --- timing ----------------------------------------------------------------


def test_timing_rejects_negative_durations() -> None:
    with pytest.raises(ValidationError):
        ScanTiming(duration_ms=-1)
    with pytest.raises(ValidationError):
        ScanTiming(normalization_duration_ms=-5)


# --- serialization ---------------------------------------------------------


def test_normalized_result_round_trips_through_json() -> None:
    result = make_result()
    restored = NormalizedScanResult.model_validate_json(result.model_dump_json())

    assert restored.metadata.scanner_name == "axe-core"
    assert restored.metadata.scanner_type == ScannerType.AXE
    assert restored.issues[0].impact == Impact.SERIOUS
    assert restored.issues[0].wcag_level == WcagLevel.AA
    assert restored.issues[0].tags == ["wcag2aa", "wcag143"]
    assert restored.timing.duration_ms == 1200


def test_normalized_result_requires_metadata() -> None:
    with pytest.raises(ValidationError):
        NormalizedScanResult.model_validate({"issues": []})


# --- summary counts --------------------------------------------------------


def test_summary_counts_are_derived_from_issues() -> None:
    issues = [
        make_issue(impact=Impact.CRITICAL),
        make_issue(impact=Impact.SERIOUS),
        make_issue(impact=Impact.SERIOUS),
        make_issue(impact=Impact.MODERATE),
        make_issue(impact=Impact.MINOR),
    ]
    result = make_result(issues=issues)

    summary = result.summary()

    assert summary.total_issues == 5
    assert summary.critical_count == 1
    assert summary.serious_count == 2
    assert summary.moderate_count == 1
    assert summary.minor_count == 1


def test_summary_counts_empty_result() -> None:
    result = make_result(issues=[])

    summary = summarize_issues(result.issues)

    assert summary.total_issues == 0
    assert summary.critical_count == 0
    assert summary.serious_count == 0
    assert summary.moderate_count == 0
    assert summary.minor_count == 0


def test_summary_counts_are_serializable() -> None:
    summary = make_result().summary()
    payload = json.loads(summary.model_dump_json())
    assert payload["total_issues"] == 1
    assert payload["critical_count"] == 0
