"""Axe-core scanner engine (Module 3B) — the first real :class:`BaseScanner`.

Flow
----
1. launch a headless Chromium via **Playwright** (lazy-imported so the rest
   of the app — and the unit-test suite — never needs the package installed),
2. navigate to the target URL (30 s timeout, HTTP >= 400 is a target error),
3. inject the vendored ``axe-core`` script (``assets/axe.min.js``,
   pinned 4.10.2; override with ``AXE_CORE_PATH``),
4. run ``axe.run`` and collect violations/passes/incomplete,
5. normalize every violation into our :class:`AccessibilityIssue` contract
   and return a :class:`NormalizedScanResult`.

Normalization is deliberately a **pure function** (``normalize_axe_result``)
so it is unit-testable without a browser; the Playwright part is a thin
driver around it. The API/service layers never see this class directly —
they consume :class:`BaseScanner` through the factory registry.

Known limitations (documented in ``docs/module3b-scanner-engine.md``):
only the entry page is scanned (``depth`` is accepted but depth > 1 is not
followed yet), and axe does not report XPath/CSS paths — those fields are
left empty until a later module derives them.
"""

import os
import re
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from app.scanners.base import BaseScanner
from app.scanners.exceptions import (
    ScannerConfigurationError,
    ScannerRuntimeError,
    ScannerTargetError,
)
from app.scanners.models import (
    AccessibilityIssue,
    Impact,
    NormalizedScanResult,
    ScanMetadata,
    ScannerType,
    ScanTiming,
    WcagLevel,
)

_AXE_VERSION = "4.10.2"
_WCAG_VERSION = "2.2"
_NAVIGATION_TIMEOUT_MS = 30_000
_DEFAULT_AXE_ASSET = Path(__file__).parent / "assets" / "axe.min.js"

# axe impact strings → controlled enum; anything unknown falls back to
# MODERATE so one malformed finding never aborts an otherwise-good scan.
_IMPACT_MAP: Dict[str, Impact] = {
    "critical": Impact.CRITICAL,
    "serious": Impact.SERIOUS,
    "moderate": Impact.MODERATE,
    "minor": Impact.MINOR,
}
_DEFAULT_IMPACT = Impact.MODERATE

# axe WCAG tags → conformance level (most specific first).
_WCAG_TAG_LEVELS: tuple = (
    ("wcag22aaa", WcagLevel.AAA),
    ("wcag21aaa", WcagLevel.AAA),
    ("wcag2aaa", WcagLevel.AAA),
    ("wcag22aa", WcagLevel.AA),
    ("wcag21aa", WcagLevel.AA),
    ("wcag2aa", WcagLevel.AA),
    ("wcag22a", WcagLevel.A),
    ("wcag21a", WcagLevel.A),
    ("wcag2a", WcagLevel.A),
)

_WHITESPACE = re.compile(r"\s+")


def _clip(value: str, limit: int) -> str:
    """Truncate ``value`` to ``limit`` characters (defensive: axe snippets
    are short, but a hostile/malformed page must not crash normalization)."""
    value = str(value or "")
    return value if len(value) <= limit else value[:limit]


def map_impact(value: Any) -> Impact:
    """Map an axe impact string onto the controlled :class:`Impact` enum."""
    if isinstance(value, str):
        mapped = _IMPACT_MAP.get(value.strip().lower())
        if mapped is not None:
            return mapped
    return _DEFAULT_IMPACT


def map_wcag_level(tags: List[str]) -> Optional[WcagLevel]:
    """Derive the WCAG conformance level from axe rule ``tags``."""
    for tag, level in _WCAG_TAG_LEVELS:
        if tag in tags:
            return level
    return None


def _node_target(node: Dict[str, Any]) -> List[str]:
    """The axe node ``target`` (list of selector parts) as a list of strings."""
    target = node.get("target")
    if isinstance(target, str):
        return [target]
    if isinstance(target, list):
        return [str(part) for part in target if str(part)]
    return []


def _node_to_issue(violation: Dict[str, Any], node: Dict[str, Any]) -> Optional[AccessibilityIssue]:
    """Normalize a single axe violation node into an :class:`AccessibilityIssue`."""
    rule_id = violation.get("id")
    if not rule_id:
        return None

    tags = [str(tag) for tag in (violation.get("tags") or []) if isinstance(tag, str) and tag.strip()]
    target_parts = _node_target(node)
    target_path = " > ".join(target_parts)

    help_text = _clip(violation.get("help") or "", 200)
    rule_name = help_text or _clip(violation.get("description") or "", 200) or _clip(str(rule_id), 200)

    return AccessibilityIssue(
        rule_id=_clip(str(rule_id), 100),
        rule_name=rule_name,
        description=_clip(violation.get("description") or "", 4000),
        help=help_text,
        help_url=_clip(violation.get("helpUrl") or "", 2048),
        impact=map_impact(node.get("impact") or violation.get("impact")),
        wcag_level=map_wcag_level(tags),
        tags=tags,
        element_selector=_clip(target_path, 2000),
        html_snippet=_clip(node.get("html") or "", 8000),
        failure_summary=_clip(node.get("failureSummary") or "", 4000),
        xpath="",
        css_path="",
        dom_path=_clip(target_path, 4000),
        screenshot_path="",
    )


def normalize_axe_result(
    axe_result: Dict[str, Any],
    *,
    metadata: ScanMetadata,
    timing: Optional[ScanTiming] = None,
) -> NormalizedScanResult:
    """Pure mapping of an ``axe.run`` result onto the normalized contract.

    Every violation node becomes one :class:`AccessibilityIssue`; malformed
    entries (missing rule id / non-dict) are skipped, never fatal.
    """
    issues: List[AccessibilityIssue] = []
    for violation in axe_result.get("violations") or []:
        if not isinstance(violation, dict):
            continue
        for node in violation.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            issue = _node_to_issue(violation, node)
            if issue is not None:
                issues.append(issue)
    return NormalizedScanResult(
        metadata=metadata,
        timing=timing or ScanTiming(),
        issues=issues,
    )


def count_tested_elements(axe_result: Dict[str, Any]) -> int:
    """Number of distinct elements axe reported across passes/violations/
    incomplete — used as ``tested_elements`` metadata (axe does not expose an
    official counter, so we count the unique node targets it reports)."""
    seen: set = set()
    for section in ("passes", "violations", "incomplete"):
        for rule in axe_result.get(section) or []:
            if not isinstance(rule, dict):
                continue
            for node in rule.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                parts = _node_target(node)
                if parts:
                    seen.add(" > ".join(parts))
    return len(seen)


def _sanitize(message: str, limit: int = 2000) -> str:
    """Collapse whitespace and truncate — never leak multi-line stack dumps."""
    cleaned = _WHITESPACE.sub(" ", str(message)).strip()
    return cleaned[:limit] or "Unknown scanner error."


def _import_playwright():
    """Lazily import the Playwright pieces ``scan`` needs.

    Kept as a module-level helper so the import failure path is unit-testable
    and the rest of the app never depends on Playwright being installed.
    """
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ScannerConfigurationError(
            "Playwright is not installed. Add 'playwright' to backend/requirements.txt "
            "and run: pip install playwright"
        ) from exc
    return PlaywrightTimeoutError, async_playwright


class AxeScanner(BaseScanner):
    """Axe-core scanner: Playwright + vendored axe-core against a target URL."""

    name = "axe-core"
    version = _AXE_VERSION
    wcag_version = _WCAG_VERSION
    scanner_type = ScannerType.AXE

    def __init__(self, axe_source: Optional[str] = None) -> None:
        """``axe_source`` overrides the vendored script (test seam)."""
        self._axe_source = axe_source

    # --- configuration -----------------------------------------------------

    def _load_axe_source(self) -> str:
        if self._axe_source:
            return self._axe_source
        override = os.environ.get("AXE_CORE_PATH", "").strip()
        path = Path(override) if override else _DEFAULT_AXE_ASSET
        if not path.is_file():
            raise ScannerConfigurationError(
                f"axe-core source not found at {path}. Set AXE_CORE_PATH or re-install the vendored asset."
            )
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ScannerConfigurationError(f"Could not read axe-core source: {_sanitize(str(exc))}") from exc

    def _browser_channel(self) -> Optional[str]:
        """Optional Playwright channel (e.g. ``chrome``) for machines without
        the bundled Chromium — configure via ``AXE_BROWSER_CHANNEL``."""
        channel = os.environ.get("AXE_BROWSER_CHANNEL", "").strip()
        return channel or None

    # --- contract ----------------------------------------------------------

    async def scan(self, url: str, *, depth: int = 1) -> NormalizedScanResult:
        if not url.lower().startswith(("http://", "https://")):
            raise ScannerTargetError(f"Invalid scan target: {_sanitize(url, 300)!r} must start with http:// or https://.")

        PlaywrightTimeoutError, async_playwright = _import_playwright()

        started = perf_counter()
        try:
            axe_source = self._load_axe_source()
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(
                        headless=True,
                        channel=self._browser_channel(),
                    )
                except Exception as exc:
                    raise ScannerConfigurationError(
                        f"Could not launch the browser: {_sanitize(str(exc))}. "
                        "Install Playwright browsers (playwright install chromium) or set AXE_BROWSER_CHANNEL."
                    ) from exc
                try:
                    page = await browser.new_page()
                    try:
                        response = await page.goto(
                            url,
                            wait_until="load",
                            timeout=_NAVIGATION_TIMEOUT_MS,
                        )
                    except PlaywrightTimeoutError as exc:
                        raise ScannerTargetError(
                            f"Timed out loading the target after {_NAVIGATION_TIMEOUT_MS // 1000}s: {_sanitize(url, 300)}"
                        ) from exc
                    if response is None:
                        raise ScannerTargetError(f"Target returned no response: {_sanitize(url, 300)}")
                    if response.status >= 400:
                        raise ScannerTargetError(
                            f"Target answered HTTP {response.status}: {_sanitize(url, 300)}"
                        )

                    await page.add_script_tag(content=axe_source)
                    axe_result = await page.evaluate(
                        """async () => {
                            const results = await axe.run(document, {
                                resultTypes: ["violations", "passes", "incomplete"]
                            });
                            return results;
                        }"""
                    )
                    # Playwright exposes `browser.version` either as a plain
                    # string or a coroutine-method depending on the release —
                    # handle both shapes.
                    _version = browser.version
                    browser_version = str(await _version()) if callable(_version) else str(_version)
                    user_agent = await page.evaluate("navigator.userAgent")
                    dom_elements = await page.evaluate("document.getElementsByTagName('*').length")
                finally:
                    await browser.close()
        except (ScannerConfigurationError, ScannerTargetError):
            raise
        except Exception as exc:
            raise ScannerRuntimeError(_sanitize(str(exc))) from exc

        if not isinstance(axe_result, dict):
            raise ScannerRuntimeError("axe-core returned a malformed result.")

        duration_ms = round((perf_counter() - started) * 1000)

        engine = axe_result.get("testEngine") or {}
        engine_version = str(engine.get("version") or self.version)

        metadata = ScanMetadata(
            scanner_name=self.name,
            scanner_type=self.scanner_type,
            scanner_version=engine_version,
            wcag_version=self.wcag_version,
            scan_url=url,
            scan_depth=depth,
            pages_scanned=1,
            browser_name="chromium",
            browser_version=browser_version,
            user_agent=user_agent,
            total_dom_elements=int(dom_elements or 0),
            tested_elements=count_tested_elements(axe_result),
        )

        norm_started = perf_counter()
        result = normalize_axe_result(axe_result, metadata=metadata)
        result.timing = ScanTiming(
            duration_ms=duration_ms,
            normalization_duration_ms=round((perf_counter() - norm_started) * 1000),
        )
        return result
