"""Tests for the Context Builder service.

The service composes persisted project + scan + issue data through the
repository protocols; in-memory fakes (same convention as the scan service
tests) exercise the full pipeline deterministically — no network, no browser,
no Supabase.

Covers: ownership, COMPLETED-only, grouping, determinism, ordering, and
malformed/missing optional fields.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.context.exceptions import ContextUnavailableError
from app.context.services import ContextBuilderService, group_issues
from app.scans.exceptions import ScanNotFoundError
from app.scans.models import ScanStatus
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel
from app.tests.test_scan_service import (
    FakeIssueRepository,
    FakeProjectRepository,
    FakeScanRepository,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def run_async(coro):
    return asyncio.run(coro)


def make_issue(rule_id: str = "color-contrast", **overrides) -> AccessibilityIssue:
    defaults = {
        "rule_id": rule_id,
        "rule_name": "Elements must have sufficient color contrast",
        "impact": Impact.SERIOUS,
        "wcag_level": WcagLevel.AA,
        "tags": ["wcag2aa", "wcag143"],
        "element_selector": "#main > p",
        "html_snippet": '<p class="muted">Low contrast</p>',
        "failure_summary": "Fix the contrast",
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


@pytest.fixture
def service() -> tuple[ContextBuilderService, FakeScanRepository, FakeIssueRepository, FakeProjectRepository]:
    scans = FakeScanRepository()
    issues = FakeIssueRepository()
    projects = FakeProjectRepository()
    svc = ContextBuilderService(scans=scans, issues=issues, projects=projects)
    return svc, scans, issues, projects


def test_build_context_for_completed_scan(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run_async(issues.insert_many(scan.id, [make_issue()]))

    doc = run_async(svc.build_for_scan("user-a", scan.id))

    assert doc.context_version == "1.0"
    assert doc.project.project_id == project.id
    assert doc.project.name == "Seed"
    assert doc.project.website_url == "https://example.com"
    assert doc.scan.scan_id == scan.id
    assert doc.scan.status is ScanStatus.COMPLETED
    assert doc.page.url == "https://example.com"
    assert doc.page.hostname == "example.com"
    assert len(doc.issues) == 1

    issue = doc.issues[0]
    assert issue.rule.rule_id == "color-contrast"
    assert issue.impact is Impact.SERIOUS
    assert issue.wcag.criteria == ["1.4.3"]
    assert issue.wcag.principle == "Perceivable"
    assert issue.wcag.level is WcagLevel.AA
    assert issue.element.tag == "p"
    assert issue.element.attributes == {"class": "muted"}
    assert issue.element.text_content == "Low contrast"
    assert issue.element.selector == "#main > p"
    assert issue.evidence.failure_summary == "Fix the contrast"
    assert issue.scanner_name == (scan.scanner_name or "")
    assert "user" not in issue.project_id  # project_id is the safe internal id


def test_build_context_foreign_scan_404(service) -> None:
    svc, scans, _issues, _projects = service
    scan = scans.seed("user-b")

    with pytest.raises(ScanNotFoundError):
        run_async(svc.build_for_scan("user-a", scan.id))


def test_build_context_missing_scan_404(service) -> None:
    svc, _scans, _issues, _projects = service
    with pytest.raises(ScanNotFoundError):
        run_async(svc.build_for_scan("user-a", "missing-scan"))


def test_build_context_requires_completed_scan(service) -> None:
    svc, scans, _issues, _projects = service
    for status in (ScanStatus.PENDING, ScanStatus.RUNNING, ScanStatus.FAILED):
        scan = scans.seed("user-a", status=status)
        with pytest.raises(ContextUnavailableError):
            run_async(svc.build_for_scan("user-a", scan.id))


def test_build_context_empty_scan(service) -> None:
    svc, scans, _issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)

    doc = run_async(svc.build_for_scan("user-a", scan.id))

    assert doc.issues == []
    assert doc.groups == []
    assert doc.page.total_issues == 0


def test_build_context_groups_are_deterministic(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run_async(
        issues.insert_many(
            scan.id,
            [
                make_issue(),  # color-contrast, #main > p
                make_issue(element_selector="#main > p"),  # same rule + same element
                make_issue(
                    rule_id="image-alt",
                    rule_name="Images must have alternative text",
                    impact=Impact.CRITICAL,
                    wcag_level=WcagLevel.A,
                    tags=["wcag2a", "wcag111"],
                    element_selector="img",
                ),
            ],
        )
    )

    doc = run_async(svc.build_for_scan("user-a", scan.id))

    group_ids = {g.group_id for g in doc.groups}
    by_type: dict = {}
    for group in doc.groups:
        by_type.setdefault(group.group_type, []).append(group)

    assert "rule:color-contrast" in group_ids
    assert "rule:image-alt" in group_ids
    assert "element:#main > p" in group_ids
    assert "wcag:1.4.3" in group_ids
    assert "wcag:1.1.1" in group_ids

    rule_group = next(g for g in doc.groups if g.group_id == "rule:color-contrast")
    assert len(rule_group.issue_ids) == 2

    element_group = next(g for g in doc.groups if g.group_id == "element:#main > p")
    assert len(element_group.issue_ids) == 2

    # Deterministic: stable ordering of groups and issue ids.
    assert [g.group_id for g in doc.groups] == sorted(g.group_id for g in doc.groups)
    for group in doc.groups:
        assert group.issue_ids == sorted(group.issue_ids)


def test_context_generation_is_reproducible(service) -> None:
    """Two builds of identical inputs produce identical content (only the
    generated_at metadata timestamp differs)."""
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run_async(issues.insert_many(scan.id, [make_issue(), make_issue(rule_id="image-alt")]))

    first = run_async(svc.build_for_scan("user-a", scan.id))
    second = run_async(svc.build_for_scan("user-a", scan.id))

    a = first.model_dump(mode="json", exclude={"generated_at"})
    b = second.model_dump(mode="json", exclude={"generated_at"})
    assert a == b


def test_issues_are_sorted_by_stable_id(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run_async(issues.insert_many(scan.id, [make_issue(), make_issue(rule_id="image-alt")]))

    doc = run_async(svc.build_for_scan("user-a", scan.id))

    ids = [i.issue_id for i in doc.issues]
    assert ids == sorted(ids)


def test_malformed_optional_fields_are_safe(service) -> None:
    svc, scans, issues, projects = service
    project = projects.seed("user-a")
    scan = scans.seed("user-a", project_id=project.id)
    run_async(
        issues.insert_many(
            scan.id,
            [
                make_issue(
                    rule_id="odd",
                    html_snippet="",
                    element_selector="",
                    tags=[],
                    wcag_level=None,
                )
            ],
        )
    )

    doc = run_async(svc.build_for_scan("user-a", scan.id))

    issue = doc.issues[0]
    assert issue.element.tag is None
    assert issue.element.attributes == {}
    assert issue.element.selector == ""
    assert issue.wcag.criteria == []
    assert issue.wcag.level is None
    assert issue.wcag.principle is None


def test_scan_project_mismatch_is_404(service) -> None:
    """If the scan references a project the caller cannot see (integrity
    break), the response is the same 404 as a foreign scan."""
    svc, scans, _issues, projects = service
    projects.seed("user-a")
    scan = scans.seed("user-a", project_id="ghost-project")

    with pytest.raises(ScanNotFoundError):
        run_async(svc.build_for_scan("user-a", scan.id))


def test_group_issues_pure_function() -> None:
    from app.context.models import IssueContext, RuleContext

    def ctx(issue_id: str) -> IssueContext:
        return IssueContext(
            issue_id=issue_id,
            scan_id="s",
            project_id="p",
            impact=Impact.MINOR,
            rule=RuleContext(rule_id="x", rule_name="Rule X", impact=Impact.MINOR),
        )

    groups = group_issues([ctx("b"), ctx("a")])
    assert [g.group_id for g in groups] == ["rule:x"]
    assert groups[0].issue_ids == ["a", "b"]
