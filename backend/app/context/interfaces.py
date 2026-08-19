"""Context Builder contract.

Routes depend on this protocol (never a concrete builder), so the
implementation can be swapped or extended (e.g. a future version that also
reads enriched context) without touching the API layer.
"""

from typing import Protocol

from app.context.models import ContextDocument


class ContextBuilder(Protocol):
    """Builds a deterministic :class:`ContextDocument` for an owned scan."""

    async def build_for_scan(self, user_id: str, scan_id: str) -> ContextDocument:
        """Return the context document for ``scan_id`` owned by ``user_id``.

        :raises ScanNotFoundError: missing or foreign scan (404-safe).
        :raises ContextUnavailableError: the scan has not completed.
        """
        ...
