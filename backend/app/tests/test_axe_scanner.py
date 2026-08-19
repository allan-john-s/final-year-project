"""Tests for the Axe-core scanner engine.

Two layers, both fully deterministic and browser-free:

- **normalization** — the pure ``axe.run`` JSON → :class:`NormalizedScanResult`
  mapping (impact mapping, WCAG tags, node fields, malformed input).
- **execution** — the ``scan()`` driver with a fake Playwright (patched via
  ``_import_playwright``), covering success, target errors, browser-launch
  failure, navigation timeout, HTTP error status, and malformed results.
"""

import asyncio
import json
from typing import Optional

import pytest

from app.scanners.axe import (
    AxeScanner,
    count_tested_elements,
    map_impact,
    map_wcag_level,
    normalize_axe_result,
)
from app.scanners.exceptions import (
    ScannerConfigurationError,
    ScannerRuntimeError,
    ScannerTargetError,
)
from app.scanners.models import (
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScannerType,
    ScanTiming,
    WcagLevel,
    calculate_accessibility_score,
)

# --- fixture helpers --------------------------------------------------------


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
        "browser_version": "128.0.0.0",
        "user_agent": "test-agent",
        "total_dom_elements": 25,
        "tested_elements": 4,
    }
    defaults.update(overrides)
    return ScanMetadata(**defaults)


def violation(**overrides) -> dict:
    data = {
        "id": "color-contrast",
        "impact": "serious",
        "tags": ["cat.color", "wcag2aa", "wcag143", "ACT"],
        "description": "Ensures the contrast between foreground and background colors meets WCAG 2 AA contrast ratio thresholds",
        "help": "Elements must have sufficient color contrast",
        "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        "nodes": [
            {
                "any": [
                    {
                        "id": "color-contrast",
                        "impact": "serious",
                        "message": "Element has insufficient color contrast (foreground color: #888888, background color: #ffffff)",
                    }
                ],
                "all": [],
                "none": [],
                "impact": "serious",
                "html": '<p style="color: #888888;">Low contrast</p>',
                "target": ["#main", "p:nth-child(1)"],
                "failureSummary": "Fix any of the following:\n  Element has insufficient color contrast",
            }
        ],
    }
    data.update(overrides)
    return data


def axe_result(violations=None) -> dict:
    return {
        "testEngine": {"name": "axe-core", "version": "4.10.2"},
        "testRunner": {"name": "axe"},
        "testEnvironment": {"userAgent": "test-agent"},
        "violations": violations if violations is not None else [violation()],
        "passes": [],
        "incomplete": [],
        "inapplicable": [],
    }


def run_async(coro):
    return asyncio.run(coro)


# --- impact / wcag mapping --------------------------------------------------


def test_map_impact_handles_every_axe_level() -> None:
    assert map_impact("critical") is Impact.CRITICAL
    assert map_impact("serious") is Impact.SERIOUS
    assert map_impact("moderate") is Impact.MODERATE
    assert map_impact("minor") is Impact.MINOR
    # Case-insensitive:
    assert map_impact("Critical") is Impact.CRITICAL


def test_map_impact_falls_back_to_moderate() -> None:
    """A malformed/unknown impact must not abort the whole scan."""
    assert map_impact("catastrophic") is Impact.MODERATE
    assert map_impact(None) is Impact.MODERATE
    assert map_impact(123) is Impact.MODERATE


def test_map_wcag_level_from_tags() -> None:
    assert map_wcag_level(["wcag2a", "cat.text"]) is WcagLevel.A
    assert map_wcag_level(["wcag2aa", "wcag143"]) is WcagLevel.AA
    assert map_wcag_level(["wcag2aaa"]) is WcagLevel.AAA
    assert map_wcag_level(["wcag21aa"]) is WcagLevel.AA
    assert map_wcag_level(["cat.color", "ACT"]) is None  # no WCAG tag


# --- normalization ----------------------------------------------------------


def test_normalize_maps_every_violation_node_to_an_issue() -> None:
    result = normalize_axe_result(axe_result(), metadata=make_metadata())

    assert isinstance(result, NormalizedScanResult)
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.rule_id == "color-contrast"
    assert issue.rule_name == "Elements must have sufficient color contrast"
    assert "contrast" in issue.description
    assert issue.help == "Elements must have sufficient color contrast"
    assert issue.help_url.startswith("https://dequeuniversity.com")
    assert issue.impact is Impact.SERIOUS
    assert issue.wcag_level is WcagLevel.AA
    assert issue.tags == ["cat.color", "wcag2aa", "wcag143", "ACT"]
    assert issue.element_selector == "#main > p:nth-child(1)"
    assert issue.dom_path == "#main > p:nth-child(1)"
    assert "Low contrast" in issue.html_snippet
    assert "insufficient color contrast" in issue.failure_summary


def test_normalize_uses_node_impact_over_rule_impact() -> None:
    result = normalize_axe_result(
        axe_result(violations=[violation(impact="minor", nodes=[{"impact": "critical", "target": ["a"], "html": "<a>x</a>"}])]),
        metadata=make_metadata(),
    )
    assert result.issues[0].impact is Impact.CRITICAL


def test_normalize_skips_malformed_entries() -> None:
    result = normalize_axe_result(
        axe_result(
            violations=[
                "not-a-dict",
                {"impact": "serious", "nodes": [{"target": ["x"], "html": "<b/>"}]},  # no rule id
                violation(),
            ]
        ),
        metadata=make_metadata(),
    )
    assert len(result.issues) == 1
    assert result.issues[0].rule_id == "color-contrast"


def test_normalize_empty_result() -> None:
    result = normalize_axe_result(axe_result(violations=[]), metadata=make_metadata())
    assert result.issues == []
    assert result.summary().total_issues == 0


def test_normalize_string_target_and_missing_fields() -> None:
    result = normalize_axe_result(
        axe_result(
            violations=[
                violation(
                    nodes=[{"target": "#hero", "html": "<div id='hero'/>"}],
                    tags=None,  # malformed — treated as no tags
                )
            ]
        ),
        metadata=make_metadata(),
    )
    issue = result.issues[0]
    assert issue.element_selector == "#hero"
    assert issue.wcag_level is None
    assert issue.tags == []


def test_count_tested_elements_counts_unique_targets() -> None:
    data = axe_result()
    data["passes"] = [{"id": "region", "nodes": [{"target": ["#main"]}, {"target": ["#footer"]}]}]
    data["violations"] = [{"id": "x", "nodes": [{"target": ["#main"]}]}]
    assert count_tested_elements(data) == 2  # #main and #footer (deduplicated)


def test_normalized_result_is_json_serializable() -> None:
    result = normalize_axe_result(axe_result(), metadata=make_metadata())
    payload = json.loads(result.model_dump_json())
    assert payload["issues"][0]["impact"] == "SERIOUS"
    assert payload["issues"][0]["wcag_level"] == "AA"


# --- accessibility score ----------------------------------------------------


def test_score_is_100_without_issues() -> None:
    assert calculate_accessibility_score([]) == 100.0


def test_score_applies_weighted_penalty() -> None:
    issues = [
        _issue(Impact.CRITICAL),
        _issue(Impact.SERIOUS),
        _issue(Impact.MODERATE),
        _issue(Impact.MINOR),
    ]
    assert calculate_accessibility_score(issues) == 82.0  # 100 - 10 - 5 - 2 - 1


def test_score_clamps_at_zero() -> None:
    many = [_issue(Impact.CRITICAL) for _ in range(50)]
    assert calculate_accessibility_score(many) == 0.0


def _issue(impact: Impact):
    from app.scanners.models import AccessibilityIssue

    return AccessibilityIssue(rule_id="r", rule_name="rule", impact=impact)


# --- scan() driver (fake Playwright) ----------------------------------------


class FakeTimeoutError(Exception):
    pass


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class FakePage:
    def __init__(self, axe_data: dict, *, status: int = 200, dom_elements: int = 25) -> None:
        self._axe = axe_data
        self._status = status
        self._dom = dom_elements

    async def goto(self, url: str, **kwargs) -> FakeResponse:
        return FakeResponse(self._status)

    async def add_script_tag(self, **kwargs) -> None:
        return None

    async def evaluate(self, expression: str):
        if "axe.run" in expression:
            return self._axe
        if "navigator.userAgent" in expression:
            return "fake-user-agent"
        return self._dom  # getElementsByTagName('*').length


class FakeBrowser:
    def __init__(self, page: FakePage, *, launch_error: Optional[Exception] = None) -> None:
        self._page = page
        self._launch_error = launch_error

    async def launch(self, **kwargs):
        if self._launch_error is not None:
            raise self._launch_error
        return self

    async def new_page(self) -> FakePage:
        return self._page

    # Some Playwright releases expose `browser.version` as a plain string
    # property (the current installed one does) — the scanner handles both.
    version = "128.0.0.0"

    async def close(self) -> None:
        return None


class FakePlaywright:
    def __init__(self, browser: FakeBrowser) -> None:
        self.chromium = browser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False


def _patch_playwright(monkeypatch, browser: FakeBrowser):
    def _import():
        return FakeTimeoutError, lambda: FakePlaywright(browser)

    monkeypatch.setattr("app.scanners.axe._import_playwright", _import)


def test_scan_success_returns_normalized_result(monkeypatch) -> None:
    _patch_playwright(monkeypatch, FakeBrowser(FakePage(axe_result())))

    result = run_async(AxeScanner(axe_source="window.axe={};").scan("https://example.com"))

    assert isinstance(result, NormalizedScanResult)
    assert result.metadata.scanner_name == "axe-core"
    assert result.metadata.scanner_type is ScannerType.AXE
    assert result.metadata.scanner_version == "4.10.2"
    assert result.metadata.wcag_version == "2.2"
    assert result.metadata.scan_url == "https://example.com"
    assert result.metadata.pages_scanned == 1
    assert result.metadata.browser_name == "chromium"
    assert result.metadata.browser_version == "128.0.0.0"
    assert result.metadata.user_agent == "fake-user-agent"
    assert result.metadata.total_dom_elements == 25
    assert result.metadata.tested_elements == 1
    assert len(result.issues) == 1
    assert result.timing.duration_ms >= 0
    assert result.timing.normalization_duration_ms >= 0


def test_scan_rejects_invalid_url_without_browser() -> None:
    with pytest.raises(ScannerTargetError):
        run_async(AxeScanner().scan("not-a-url"))
    with pytest.raises(ScannerTargetError):
        run_async(AxeScanner().scan("ftp://example.com"))


def test_scan_missing_playwright_raises_configuration_error(monkeypatch) -> None:
    def _import():
        raise ScannerConfigurationError("Playwright is not installed.")

    monkeypatch.setattr("app.scanners.axe._import_playwright", _import)
    with pytest.raises(ScannerConfigurationError):
        run_async(AxeScanner().scan("https://example.com"))


def test_scan_browser_launch_failure_is_configuration_error(monkeypatch) -> None:
    _patch_playwright(
        monkeypatch,
        FakeBrowser(FakePage(axe_result()), launch_error=RuntimeError("exec: no browser")),
    )
    with pytest.raises(ScannerConfigurationError) as excinfo:
        run_async(AxeScanner().scan("https://example.com"))
    assert "no browser" in str(excinfo.value)
    assert "example.com" not in str(excinfo.value)  # sanitized, no target leakage beyond intent


def test_scan_navigation_timeout_is_target_error(monkeypatch) -> None:
    class FailingPage(FakePage):
        async def goto(self, url: str, **kwargs) -> FakeResponse:
            raise FakeTimeoutError("Timeout 30000ms exceeded")

    _patch_playwright(monkeypatch, FakeBrowser(FailingPage(axe_result())))
    with pytest.raises(ScannerTargetError) as excinfo:
        run_async(AxeScanner().scan("https://example.com"))
    assert "Timed out" in str(excinfo.value)


def test_scan_http_error_status_is_target_error(monkeypatch) -> None:
    _patch_playwright(monkeypatch, FakeBrowser(FakePage(axe_result(), status=503)))
    with pytest.raises(ScannerTargetError) as excinfo:
        run_async(AxeScanner().scan("https://example.com"))
    assert "HTTP 503" in str(excinfo.value)


def test_scan_malformed_axe_result_is_runtime_error(monkeypatch) -> None:
    _patch_playwright(monkeypatch, FakeBrowser(FakePage("not-a-dict")))
    with pytest.raises(ScannerRuntimeError):
        run_async(AxeScanner().scan("https://example.com"))


def test_scan_missing_axe_source_is_configuration_error(monkeypatch) -> None:
    _patch_playwright(monkeypatch, FakeBrowser(FakePage(axe_result())))
    monkeypatch.setenv("AXE_CORE_PATH", "/nonexistent/axe.min.js")
    with pytest.raises(ScannerConfigurationError) as excinfo:
        run_async(AxeScanner().scan("https://example.com"))
    assert "axe-core source not found" in str(excinfo.value)
