"""Remediation domain (Module 7).

Proposes actionable remediation for ranked accessibility strategies.
Deliberately review-first: proposals are never automatically applied.
"""

from app.remediations.models import (
    RemediationProposal,
    RemediationStatus,
    REMEDIATION_VERSION,
)

__all__ = [
    "REMEDIATION_VERSION",
    "RemediationProposal",
    "RemediationStatus",
]
