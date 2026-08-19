"""Mock remediation provider — deterministic, no LLM, no network.

Produces realistic remediation proposals for testing and development.
The output is fully deterministic given the same inputs.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.remediations.models import RemediationProposal, ProposedChange


class MockRemediationProvider:
    """Deterministic remediation provider for testing and development."""

    name = "mock"

    async def generate_proposal(
        self,
        *,
        scan_id: str,
        issue_id: str,
        strategy_id: str,
        rank: int,
        issue_description: str,
        strategy_title: str,
        strategy_summary: str,
        strategy_rationale: str,
        implementation_steps: list[str],
        element_html: str,
        element_selector: str,
        wcag_criteria: list[str],
    ) -> RemediationProposal:
        """Generate a deterministic remediation proposal."""
        # Generate before/after based on the element HTML
        before_code = element_html.strip() if element_html else "<element>Missing content</element>"

        # Create a simple "after" by adding ARIA attributes
        if "aria-label" in before_code:
            after_code = before_code  # Already has aria-label
        elif "<" in before_code:
            after_code = before_code.replace(">", ' aria-label="Accessible label">', 1) if ">" in before_code else before_code + ' aria-label="Accessible label"'
        else:
            after_code = f'<div aria-label="Accessible">{before_code}</div>'

        wcag_text = ", ".join(wcag_criteria) if wcag_criteria else "WCAG 2.1"

        return RemediationProposal(
            id=f"rem-{uuid4().hex[:12]}",
            scan_id=scan_id,
            issue_id=issue_id,
            strategy_id=strategy_id,
            rank=rank,
            title=f"Remediate: {strategy_title}",
            summary=f"Apply '{strategy_title}' to fix the accessibility issue. {strategy_summary}",
            rationale=(
                f"This remediation follows the recommended strategy (rank #{rank}) "
                f"because {strategy_rationale.lower()} "
                f"The fix targets {wcag_text} compliance."
            ),
            implementation_steps=implementation_steps[:5] if implementation_steps else [
                "Locate the affected element in the source code",
                "Apply the recommended change",
                "Test with screen reader",
                "Verify WCAG compliance",
                "Update automated tests",
            ],
            proposed_change=ProposedChange(
                before=before_code,
                after=after_code,
                file_path=element_selector if element_selector else None,
                explanation=(
                    f"Modified the element to improve accessibility. "
                    f"This addresses {wcag_text} requirements."
                ),
            ),
            affected_element=element_selector or "Unknown element",
            expected_improvement=(
                f"Expected to resolve the {issue_description} issue and improve "
                f"WCAG {wcag_text} compliance."
            ),
            risks=[
                "Visual layout may shift slightly",
                "JavaScript event handlers may need adjustment",
            ],
            validation_steps=[
                "Run automated accessibility scan",
                "Test with NVDA/JAWS screen reader",
                "Verify keyboard navigation",
                "Check color contrast ratios",
                "Validate HTML semantics",
            ],
            provider=self.name,
            confidence=min(0.85, 0.6 + rank * 0.05),
            status="PROPOSED",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
