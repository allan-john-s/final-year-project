"""In-memory store for remediation proposals (Module 7).

Provides persistence for proposals during development/testing. In production,
this would be replaced by a Supabase-backed repository with RLS.

This store is NOT safe for concurrent access in production — it's intended
for single-process development and testing only.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.remediations.models import RemediationProposal, RemediationStatus


class RemediationStore:
    """Simple in-memory store for remediation proposals."""

    def __init__(self) -> None:
        self._proposals: Dict[str, RemediationProposal] = {}

    def save(self, proposal: RemediationProposal) -> RemediationProposal:
        """Save a proposal."""
        self._proposals[proposal.id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Optional[RemediationProposal]:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def list_for_scan(
        self,
        scan_id: str,
        user_id: str,
    ) -> List[RemediationProposal]:
        """List proposals for a scan owned by the user."""
        return [
            p
            for p in self._proposals.values()
            if p.scan_id == scan_id
        ]

    def update_status(
        self,
        proposal_id: str,
        status: RemediationStatus,
    ) -> RemediationProposal:
        """Update a proposal's status."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"Proposal {proposal_id} not found")
        
        updated = proposal.model_copy(
            update={
                "status": status,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._proposals[proposal_id] = updated
        return updated


# Global singleton for development/testing
_remediation_store = RemediationStore()


def get_remediation_store() -> RemediationStore:
    """Get the global remediation store."""
    return _remediation_store
