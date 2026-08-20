"""API schemas for measurement endpoints (Module 8).

The request identifies the follow-up scan to compare against the original.
The server validates ownership, scan status, and ordering.
"""

from pydantic import BaseModel, Field


class MeasureRequest(BaseModel):
    """Body for ``POST /api/v1/remediations/{remediation_id}/measure``.

    Identifies the follow-up scan. The original scan is derived from the
    remediation proposal.
    """

    followup_scan_id: str = Field(min_length=1, max_length=64)
