"""Tests for the context domain models.

Pure model validation — no network, no repositories. Covers required fields,
defaults, versioning, and JSON serialization of the full ContextDocument.
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.context.models import (
    CONTEXT_VERSION,
    ContextDocument,
    ElementContext,
    EvidenceContext,
    IssueContext,
    IssueGroup,
    PageContext,
    ProjectContext,
    RuleContext,
    ScanContext,
    WcagContext,
)
from app.projects.models import ProjectStatus
from app.scans.models import ScanStatus
from app.scanners.models import Impact, ScannerType, WcagLevel


def make_project_context(**overrides) -> ProjectContext:
    defaults = {
        "project_id": "project-1",
        "name": "My site",
        "description": "",
        "website_url": "https://example.com",
        "status": ProjectStatus.SCANNED,
    }
    defaults.update(overrides)
    return ProjectContext(**defaults)


def make_scan_context(**overrides) -> ScanContext:
    defaults = {
        "scan_id": "scan-1",
        "project_id": "project-1",
        "scanner_type": ScannerType.AXE,
        "status": ScanStatus.COMPLETED,
        "scanner_name": "axe-core",
        "scanner_version": "4.10.2",
        "wcag_version": "2.2",
        "scan_url": "https://example.com",
        "scan_depth": 1,
        "pages_scanned": 1,
        "accessibility_score": 90.0,
        "total_issues": 1,
        "critical_count": 0,
        "serious_count": 1,
        "moderate_count": 0,
        "minor_count": 0,
    }
    defaults.update(overrides)
    return ScanContext(**defaults)


def make_page_context(**overrides) -> PageContext:
    defaults = {
        "url": "https://example.com",
        "hostname": "example.com",
        "pathname": "/",
        "scanned_at": datetime.now(timezone.utc),
        "total_issues": 1,
        "accessibility_score": 90.0,
    }
    defaults.update(overrides)
    return PageContext(**defaults)


def make_wcag(**overrides) -> WcagContext:
    defaults = {
        "wcag_version": "2.2",
        "level": WcagLevel.AA,
        "tags": ["wcag2aa", "wcag143"],
        "criteria": ["1.4.3"],
        "principle": "Perceivable",
    }
    defaults.update(overrides)
    return WcagContext(**defaults)


def make_rule(**overrides) -> RuleContext:
    defaults = {
        "rule_id": "color-contrast",
        "rule_name": "Elements must have sufficient color contrast",
        "description": "Ensures contrast meets WCAG 2 AA thresholds",
        "help": "Elements must have sufficient color contrast",
        "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        "impact": Impact.SERIOUS,
        "tags": ["wcag2aa", "wcag143"],
        "wcag": make_wcag(),
    }
    defaults.update(overrides)
    return RuleContext(**defaults)


def make_issue_context(**overrides) -> IssueContext:
    defaults = {
        "issue_id": "issue-1",
        "scan_id": "scan-1",
        "project_id": "project-1",
        "rule": make_rule(),
        "impact": Impact.SERIOUS,
        "wcag": make_wcag(),
        "element": ElementContext(
            html="<p>Low contrast</p>",
            tag="p",
            attributes={"class": "muted"},
            selector="#main > p",
            text_content="Low contrast",
        ),
        "evidence": EvidenceContext(failure_summary="Fix the contrast"),
        "scanner_name": "axe-core",
        "scanner_version": "4.10.2",
    }
    defaults.update(overrides)
    return IssueContext(**defaults)


def make_document(**overrides) -> ContextDocument:
    defaults = {
        "project": make_project_context(),
        "scan": make_scan_context(),
        "page": make_page_context(),
        "issues": [make_issue_context()],
        "groups": [
            IssueGroup(group_id="rule:color-contrast", group_type="same_rule", label="Color contrast", issue_ids=["issue-1"])
        ],
    }
    defaults.update(overrides)
    return ContextDocument(**defaults)


def test_document_requires_project_scan_page() -> None:
    with pytest.raises(ValidationError):
        ContextDocument()
    with pytest.raises(ValidationError):
        ContextDocument(project=make_project_context(), page=make_page_context())  # no scan


def test_document_defaults_to_current_version() -> None:
    doc = make_document()
    assert doc.context_version == "1.0"
    assert doc.context_version == CONTEXT_VERSION
    assert doc.generated_at is not None


def test_issue_context_requires_rule_identity() -> None:
    with pytest.raises(ValidationError):
        make_issue_context(rule=None)
    with pytest.raises(ValidationError):
        IssueContext(issue_id="x", scan_id="s", project_id="p", impact=Impact.MINOR)  # no rule


def test_issue_group_requires_type_and_id() -> None:
    with pytest.raises(ValidationError):
        IssueGroup(group_id="", group_type="same_rule")
    group = IssueGroup(group_id="rule:x", group_type="same_rule", label="X", issue_ids=["a", "b"])
    assert group.issue_ids == ["a", "b"]


def test_optional_element_fields_default_safely() -> None:
    element = ElementContext()
    assert element.html == ""
    assert element.tag is None
    assert element.attributes == {}
    assert element.aria == {}
    assert element.form == {}
    assert element.text_content == ""


def test_document_round_trips_through_json() -> None:
    doc = make_document()
    restored = ContextDocument.model_validate_json(doc.model_dump_json())

    assert restored.context_version == "1.0"
    assert restored.project.name == "My site"
    assert restored.scan.scanner_name == "axe-core"
    assert restored.issues[0].rule.rule_id == "color-contrast"
    assert restored.issues[0].impact is Impact.SERIOUS
    assert restored.issues[0].wcag.principle == "Perceivable"
    assert restored.groups[0].group_id == "rule:color-contrast"
    assert restored.generated_at == doc.generated_at


def test_document_serialization_has_no_user_identity() -> None:
    """Context never exposes user_id or any credential-like field."""
    payload = json.loads(make_document().model_dump_json())

    def walk(node, path: str = "") -> list:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if "user" in key.lower() or "secret" in key.lower() or "token" in key.lower():
                    found.append(f"{path}.{key}")
                found.extend(walk(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                found.extend(walk(item, f"{path}[{index}]"))
        return found

    assert walk(payload) == []
