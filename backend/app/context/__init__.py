"""Context Builder subsystem (Module 3C).

Deterministically transforms a completed scan's persisted data into a
versioned, machine-readable :class:`ContextDocument` — the structured
evidence for future strategy-generation modules. No AI, no remediation
advice, no secrets.
"""

from app.context.exceptions import ContextError, ContextUnavailableError
from app.context.interfaces import ContextBuilder
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
from app.context.services import ContextBuilderService, group_issues

__all__ = [
    "CONTEXT_VERSION",
    "ContextBuilder",
    "ContextBuilderService",
    "ContextDocument",
    "ContextError",
    "ContextUnavailableError",
    "ElementContext",
    "EvidenceContext",
    "IssueContext",
    "IssueGroup",
    "PageContext",
    "ProjectContext",
    "RuleContext",
    "ScanContext",
    "WcagContext",
    "group_issues",
]
