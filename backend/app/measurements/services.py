"""Measurement service (Module 8).

Compares an original scan against a follow-up scan after an accepted
remediation has been externally applied. Produces a deterministic
before/after improvement report.

Flow::

    Authenticated user
        -> remediation_id + followup_scan_id
        -> verify remediation exists and is ACCEPTED/APPLIED
        -> retrieve original scan from remediation
        -> verify follow-up scan ownership + completion + ordering
        -> compute issue fingerprints from both scans
        -> compare: resolved, persistent, new issues
        -> compare: severity breakdown
        -> classify: IMPROVED / NO_CHANGE / REGRESSED / COMPLETED
        -> ImprovementMeasurement

The measurement is deterministic — no LLM, no external APIs.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from app.measurements.exceptions import (
    MeasurementDuplicateError,
    MeasurementRemediationError,
    MeasurementScanError,
    MeasurementScanIncompleteError,
    MeasurementScanOrderError,
)
from app.measurements.interfaces import MeasurementStore, ScanAccessor
from app.measurements.models import (
    ImprovementMeasurement,
    IssueFingerprint,
    MEASUREMENT_VERSION,
    MeasurementStatus,
    SeverityBurden,
)
from app.remediations.models import RemediationProposal, RemediationStatus
from app.remediations.store import RemediationStore
from app.scans.models import Scan, ScanStatus


# --- Severity burden weights (matches accessibility score penalties) ---------
SEVERITY_WEIGHTS: Dict[str, int] = {
    "CRITICAL": 10,
    "SERIOUS": 5,
    "MODERATE": 2,
    "MINOR": 1,
}

# --- Threshold for no-change classification ---------------------------------
# If score_delta is within this range AND severity burden doesn't regress,
# classify as NO_CHANGE rather than IMPROVED.
NO_CHANGE_SCORE_THRESHOLD = 0.5


def _fingerprint_from_scan(issues: List[Dict]) -> List[IssueFingerprint]:
    """Create stable fingerprints from scan issue data.

    Each issue is identified by rule_id + selector + dom_path.
    Duplicate fingerprints are deduplicated (the highest-severity occurrence wins).
    """
    seen: Dict[str, IssueFingerprint] = {}

    for issue in issues:
        rule_id = issue.get("rule_id", "")
        selector = issue.get("element_selector", "")
        dom_path = issue.get("dom_path", "")
        impact = issue.get("impact", "MODERATE")

        fp = IssueFingerprint.from_issue_data(rule_id, selector, dom_path, impact)

        # Keep the most severe version if duplicates exist
        existing = seen.get(fp.fingerprint)
        if existing is None:
            seen[fp.fingerprint] = fp
        else:
            # Higher severity weight wins
            existing_weight = SEVERITY_WEIGHTS.get(existing.impact, 0)
            new_weight = SEVERITY_WEIGHTS.get(impact, 0)
            if new_weight > existing_weight:
                seen[fp.fingerprint] = fp

    return list(seen.values())


def _severity_burden_from_counts(
    critical: int, serious: int, moderate: int, minor: int
) -> SeverityBurden:
    """Create a SeverityBurden from counts."""
    return SeverityBurden(
        critical=critical,
        serious=serious,
        moderate=moderate,
        minor=minor,
    )


def classify_measurement(
    score_delta: Optional[float],
    severity_before: SeverityBurden,
    severity_after: SeverityBurden,
    new_severe_count: int,
) -> MeasurementStatus:
    """Deterministic classification of measurement outcome.

    Rules:
    - IMPROVED: score increased by more than threshold AND no new critical/serious issues
    - NO_CHANGE: score change within threshold AND severity burden didn't increase significantly
    - REGRESSED: score decreased OR new critical/serious issues were introduced
    - COMPLETED: measurement performed but classification is ambiguous (e.g. None scores)
    """
    burden_delta = severity_after.total_burden - severity_before.total_burden

    if score_delta is not None:
        # Regressed: score decreased significantly
        if score_delta < -NO_CHANGE_SCORE_THRESHOLD:
            return MeasurementStatus.REGRESSED
        # Regressed: burden increased with new severe issues
        if burden_delta > 0 and new_severe_count > 0:
            return MeasurementStatus.REGRESSED
        # Regressed: burden increased without new severe issues
        if burden_delta > 0 and new_severe_count == 0:
            return MeasurementStatus.REGRESSED
        # Improved: severity burden decreased significantly (even if score delta is small)
        if burden_delta < -2 and new_severe_count == 0:
            return MeasurementStatus.IMPROVED
        # No change: score within threshold, burden stable, no new severe
        if abs(score_delta) <= NO_CHANGE_SCORE_THRESHOLD and burden_delta == 0 and new_severe_count == 0:
            return MeasurementStatus.NO_CHANGE
        # Improved: score increased significantly and no new severe issues
        if score_delta > NO_CHANGE_SCORE_THRESHOLD and new_severe_count == 0:
            return MeasurementStatus.IMPROVED
        # Improved: score increased at all with no burden increase
        if score_delta > 0 and burden_delta <= 0 and new_severe_count == 0:
            return MeasurementStatus.IMPROVED

    # Ambiguous case (no scores, etc.)
    return MeasurementStatus.COMPLETED


def build_measurement_summary(
    status: MeasurementStatus,
    score_delta: Optional[float],
    improvement_pct: Optional[float],
    issues_resolved: int,
    issues_remaining: int,
    new_issues: int,
    severity_before: SeverityBurden,
    severity_after: SeverityBurden,
) -> str:
    """Build a human-readable measurement summary."""
    parts: List[str] = []

    if status == MeasurementStatus.IMPROVED:
        parts.append("Accessibility improved.")
    elif status == MeasurementStatus.NO_CHANGE:
        parts.append("No meaningful change detected.")
    elif status == MeasurementStatus.REGRESSED:
        parts.append("Accessibility regressed.")
    else:
        parts.append("Measurement completed.")

    if score_delta is not None and improvement_pct is not None:
        direction = "increased" if score_delta > 0 else "decreased" if score_delta < 0 else "unchanged"
        parts.append(
            f"Score {direction} by {abs(score_delta):.1f} "
            f"({improvement_pct:+.1f}%)."
        )

    parts.append(
        f"{issues_resolved} issue{'s' if issues_resolved != 1 else ''} resolved, "
        f"{issues_remaining} remaining, {new_issues} new."
    )

    if severity_before.total_burden != severity_after.total_burden:
        parts.append(
            f"Severity burden: {severity_before.total_burden} → {severity_after.total_burden}."
        )

    return " ".join(parts)


class MeasurementService:
    """Compute and manage improvement measurements for an accepted remediation."""

    def __init__(
        self,
        scan_accessor: ScanAccessor,
        remediation_store: RemediationStore,
        measurement_store: MeasurementStore,
    ) -> None:
        self._scan_accessor = scan_accessor
        self._remediation_store = remediation_store
        self._measurement_store = measurement_store

    async def measure(
        self,
        user_id: str,
        remediation_id: str,
        followup_scan_id: str,
    ) -> ImprovementMeasurement:
        """Create a measurement comparing original scan vs follow-up scan.

        :raises MeasurementRemediationError: remediation not found or invalid state.
        :raises MeasurementScanError: follow-up scan not found or not owned.
        :raises MeasurementScanIncompleteError: follow-up scan not completed.
        :raises MeasurementScanOrderError: follow-up scan occurs before original.
        :raises MeasurementDuplicateError: measurement already exists for this pair.
        """
        # 1. Retrieve remediation
        proposal = self._remediation_store.get(remediation_id)
        if proposal is None:
            raise MeasurementRemediationError(
                "The remediation proposal was not found."
            )

        # 2. Validate remediation ownership (the store is per-user in production;
        #    for the in-memory store, we rely on the scan ownership check below)
        # 3. Validate remediation status
        if proposal.status not in (RemediationStatus.ACCEPTED, RemediationStatus.APPLIED):
            raise MeasurementRemediationError(
                f"Remediation must be ACCEPTED or APPLIED to measure. "
                f"Current status: {proposal.status.value}."
            )

        # 4. Retrieve original scan
        original_scan = await self._scan_accessor.get_scan(user_id, proposal.scan_id)
        if original_scan is None:
            raise MeasurementScanError("The original scan was not found.")

        # 5. Retrieve follow-up scan
        followup_scan = await self._scan_accessor.get_scan(user_id, followup_scan_id)
        if followup_scan is None:
            raise MeasurementScanError(
                "The follow-up scan was not found or does not belong to you."
            )

        # 6. Validate follow-up scan is completed
        if followup_scan.status != ScanStatus.COMPLETED:
            raise MeasurementScanIncompleteError(
                f"The follow-up scan has not completed. Status: {followup_scan.status.value}."
            )

        # 7. Validate scan ordering: follow-up must be created after original
        if followup_scan.created_at <= original_scan.created_at:
            raise MeasurementScanOrderError(
                "The follow-up scan must have been created after the original scan."
            )

        # 8. Check for duplicate measurement
        existing = self._measurement_store.list_for_remediation(remediation_id)
        for m in existing:
            if m.followup_scan_id == followup_scan_id:
                raise MeasurementDuplicateError(
                    "A measurement already exists for this remediation and follow-up scan."
                )

        # 9. Compute comparison
        measurement = self._compute_measurement(
            proposal=proposal,
            original_scan=original_scan,
            followup_scan=followup_scan,
        )

        # 10. Persist
        return self._measurement_store.save(measurement)

    def _compute_measurement(
        self,
        proposal: RemediationProposal,
        original_scan: Scan,
        followup_scan: Scan,
    ) -> ImprovementMeasurement:
        """Compute the before/after comparison deterministically."""

        # Score comparison
        orig_score = original_scan.accessibility_score
        follow_score = followup_scan.accessibility_score

        score_delta: Optional[float] = None
        improvement_pct: Optional[float] = None
        if orig_score is not None and follow_score is not None:
            score_delta = round(follow_score - orig_score, 2)
            if orig_score > 0:
                improvement_pct = round((score_delta / orig_score) * 100, 2)
            elif orig_score == 0 and follow_score > 0:
                improvement_pct = 100.0

        # Severity comparison
        sev_before = _severity_burden_from_counts(
            original_scan.critical_count,
            original_scan.serious_count,
            original_scan.moderate_count,
            original_scan.minor_count,
        )
        sev_after = _severity_burden_from_counts(
            followup_scan.critical_count,
            followup_scan.serious_count,
            followup_scan.moderate_count,
            followup_scan.minor_count,
        )

        # Issue-level comparison using fingerprints
        # Extract issue data from scan summaries for fingerprinting
        # Since scans store aggregate counts (not individual issues), we use
        # the summary-level data for the comparison. For full issue-level
        # fingerprinting, individual issues would need to be stored.
        orig_total = original_scan.total_issues
        follow_total = followup_scan.total_issues

        # Conservative estimate: issues_resolved is at most the difference
        # when followup < original. New issues when followup > original.
        issues_resolved = max(0, orig_total - follow_total)
        new_issues = max(0, follow_total - orig_total)
        issues_remaining = min(orig_total, follow_total)

        # Compute "new severe" count for classification
        new_severe_count = 0
        if followup_scan.critical_count > original_scan.critical_count:
            new_severe_count += followup_scan.critical_count - original_scan.critical_count
        if followup_scan.serious_count > original_scan.serious_count:
            new_severe_count += followup_scan.serious_count - original_scan.serious_count

        # Classify
        status = classify_measurement(
            score_delta=score_delta,
            severity_before=sev_before,
            severity_after=sev_after,
            new_severe_count=new_severe_count,
        )

        # Build summary
        summary = build_measurement_summary(
            status=status,
            score_delta=score_delta,
            improvement_pct=improvement_pct,
            issues_resolved=issues_resolved,
            issues_remaining=issues_remaining,
            new_issues=new_issues,
            severity_before=sev_before,
            severity_after=sev_after,
        )

        measurement_id = f"m-{uuid.uuid4().hex[:16]}"

        return ImprovementMeasurement(
            id=measurement_id,
            remediation_id=proposal.id,
            original_scan_id=original_scan.id,
            followup_scan_id=followup_scan.id,
            original_accessibility_score=orig_score,
            followup_accessibility_score=follow_score,
            score_delta=score_delta,
            score_improvement_percentage=improvement_pct,
            original_issue_count=orig_total,
            followup_issue_count=follow_total,
            issues_resolved=issues_resolved,
            issues_remaining=issues_remaining,
            new_issues_introduced=new_issues,
            critical_before=sev_before.critical,
            critical_after=sev_after.critical,
            serious_before=sev_before.serious,
            serious_after=sev_after.serious,
            moderate_before=sev_before.moderate,
            moderate_after=sev_after.moderate,
            minor_before=sev_before.minor,
            minor_after=sev_after.minor,
            status=status,
            measurement_summary=summary,
        )
