"""Context Builder service (Module 3C).

Transforms a completed scan's persisted data (project + scan + normalized
issues) into a deterministic, versioned :class:`ContextDocument` — the
structured evidence future strategy-generation modules will consume.

Pipeline (all reads go through the existing repositories, never Supabase):

1. load the scan scoped to the authenticated user (404 for missing/foreign),
2. require the scan to be COMPLETED (409 otherwise),
3. load the owning project (defense-in-depth ownership check),
4. load the normalized issues for the scan,
5. build project / scan / page / rule+WCAG / element / evidence context,
6. group issues deterministically (same rule, same element, same WCAG
   criterion),
7. return the versioned :class:`ContextDocument`.

Determinism: issues are sorted by stable issue id, groups by stable key,
tags/criteria are sorted, and ``generated_at`` is metadata only — identical
inputs always produce identical context content.
"""

from typing import Dict, List
from urllib.parse import urlparse

from app.context.exceptions import ContextUnavailableError
from app.context.mapping import extract_element_info, wcag_criteria, wcag_principle
from app.context.models import (
    CONTEXT_VERSION,
    ContextDocument,
    EvidenceContext,
    IssueContext,
    IssueGroup,
    PageContext,
    ProjectContext,
    RuleContext,
    ScanContext,
    WcagContext,
)
from app.projects.models import Project
from app.projects.interfaces import ProjectRepository
from app.scans.exceptions import ScanNotFoundError
from app.scans.interfaces import AccessibilityIssueRepository, ScanRepository
from app.scans.models import Scan, ScanStatus, StoredAccessibilityIssue


class ContextBuilderService:
    """Deterministic context construction for owned, completed scans."""

    def __init__(
        self,
        scans: ScanRepository,
        issues: AccessibilityIssueRepository,
        projects: ProjectRepository,
    ) -> None:
        self._scans = scans
        self._issues = issues
        self._projects = projects

    # --- public API ----------------------------------------------------------

    async def build_for_scan(self, user_id: str, scan_id: str) -> ContextDocument:
        scan = await self._scans.get(user_id, scan_id)
        if scan is None:
            raise ScanNotFoundError("Scan not found.")

        if scan.status != ScanStatus.COMPLETED:
            raise ContextUnavailableError(
                "Context is only available for completed scans."
            )

        project = await self._projects.get(user_id, scan.project_id)
        if project is None:
            # Integrity guard: the scan row references a project the caller
            # cannot see — answer the same 404 as a foreign/missing scan.
            raise ScanNotFoundError("Scan not found.")

        issues = await self._issues.list_for_scan(user_id, scan_id)

        return self._build_document(scan, project, issues)

    # --- construction --------------------------------------------------------

    def _build_document(
        self,
        scan: Scan,
        project: Project,
        issues: List[StoredAccessibilityIssue],
    ) -> ContextDocument:
        project_context = self._project_context(project)
        scan_context = self._scan_context(scan)
        page_context = self._page_context(scan)

        issue_contexts = [
            self._issue_context(scan, project.id, issue)
            for issue in sorted(issues, key=lambda i: i.id)
        ]

        return ContextDocument(
            context_version=CONTEXT_VERSION,
            project=project_context,
            scan=scan_context,
            page=page_context,
            issues=issue_contexts,
            groups=group_issues(issue_contexts),
        )

    @staticmethod
    def _project_context(project: Project) -> ProjectContext:
        return ProjectContext(
            project_id=project.id,
            name=project.name,
            description=project.description or "",
            website_url=project.website_url,
            status=project.status,
        )

    @staticmethod
    def _scan_context(scan: Scan) -> ScanContext:
        return ScanContext(
            scan_id=scan.id,
            project_id=scan.project_id,
            scanner_type=scan.scanner_type,
            status=scan.status,
            scanner_name=scan.scanner_name,
            scanner_version=scan.scanner_version,
            wcag_version=scan.wcag_version,
            scan_url=scan.scan_url,
            scan_depth=scan.scan_depth,
            pages_scanned=scan.pages_scanned,
            started_at=scan.started_at,
            completed_at=scan.completed_at,
            duration_ms=scan.duration_ms,
            total_dom_elements=scan.total_dom_elements,
            tested_elements=scan.tested_elements,
            accessibility_score=scan.accessibility_score,
            total_issues=scan.total_issues,
            critical_count=scan.critical_count,
            serious_count=scan.serious_count,
            moderate_count=scan.moderate_count,
            minor_count=scan.minor_count,
        )

    @staticmethod
    def _page_context(scan: Scan) -> PageContext:
        url = scan.scan_url or ""
        parsed = urlparse(url)
        return PageContext(
            url=url,
            hostname=parsed.hostname or "",
            pathname=parsed.path or "",
            scanned_at=scan.completed_at or scan.started_at,
            duration_ms=scan.duration_ms,
            scanner=scan.scanner_name,
            scanner_version=scan.scanner_version,
            total_issues=scan.total_issues,
            critical_count=scan.critical_count,
            serious_count=scan.serious_count,
            moderate_count=scan.moderate_count,
            minor_count=scan.minor_count,
            accessibility_score=scan.accessibility_score,
        )

    def _issue_context(
        self,
        scan: Scan,
        project_id: str,
        issue: StoredAccessibilityIssue,
    ) -> IssueContext:
        criteria = wcag_criteria(issue.tags)
        wcag = WcagContext(
            wcag_version=scan.wcag_version,
            level=issue.wcag_level,
            tags=sorted(set(issue.tags)),
            criteria=criteria,
            principle=wcag_principle(criteria),
        )
        return IssueContext(
            issue_id=issue.id,
            scan_id=scan.id,
            project_id=project_id,
            rule=RuleContext(
                rule_id=issue.rule_id,
                rule_name=issue.rule_name,
                description=issue.description or "",
                help=issue.help or "",
                help_url=issue.help_url or "",
                impact=issue.impact,
                tags=sorted(set(issue.tags)),
                wcag=wcag,
            ),
            impact=issue.impact,
            wcag=wcag,
            element=extract_element_info(issue.html_snippet or "").model_copy(
                update={
                    "selector": issue.element_selector or "",
                    "dom_path": issue.dom_path or "",
                }
            ),
            evidence=EvidenceContext(
                failure_summary=issue.failure_summary or "",
                xpath=issue.xpath or "",
                css_path=issue.css_path or "",
                screenshot_path=issue.screenshot_path or "",
            ),
            scanner_name=scan.scanner_name or "",
            scanner_version=scan.scanner_version or "",
        )


def group_issues(issues: List[IssueContext]) -> List[IssueGroup]:
    """Deterministic, explainable issue grouping.

    Groups (all keys are stable and sorted):

    - ``same_rule`` — every issue of the same axe rule (``rule:<rule_id>``),
    - ``same_element`` — every issue targeting the same element
      (``element:<selector>``),
    - ``wcag`` — every issue sharing a WCAG criterion (``wcag:<criterion>``).

    No ML, no embeddings, no LLM — pure deterministic grouping for later
    strategy modules.
    """
    groups: Dict[str, IssueGroup] = {}

    for issue in sorted(issues, key=lambda i: i.issue_id):
        rule_id = issue.rule.rule_id
        _add_group(
            groups,
            group_id=f"rule:{rule_id}",
            group_type="same_rule",
            label=issue.rule.rule_name or rule_id,
            issue_id=issue.issue_id,
        )

        selector = issue.element.selector.strip() if issue.element.selector else ""
        if selector:
            _add_group(
                groups,
                group_id=f"element:{selector}",
                group_type="same_element",
                label=f"Same element: {selector}",
                issue_id=issue.issue_id,
            )

        for criterion in issue.wcag.criteria:
            _add_group(
                groups,
                group_id=f"wcag:{criterion}",
                group_type="wcag",
                label=f"WCAG {criterion}",
                issue_id=issue.issue_id,
            )

    return sorted(
        (group for group in groups.values() if len(group.issue_ids) > 0),
        key=lambda g: g.group_id,
    )


def _add_group(
    groups: Dict[str, IssueGroup],
    *,
    group_id: str,
    group_type: str,
    label: str,
    issue_id: str,
) -> None:
    group = groups.get(group_id)
    if group is None:
        group = IssueGroup(group_id=group_id, group_type=group_type, label=label)
        groups[group_id] = group
    if issue_id not in group.issue_ids:
        group.issue_ids.append(issue_id)
        group.issue_ids.sort()
