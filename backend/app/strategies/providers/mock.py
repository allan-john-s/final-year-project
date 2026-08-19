"""Deterministic mock strategy provider.

Generates genuinely different candidate strategies from the *actual* issue
context (rule, WCAG criteria, element evidence) — no LLM is involved. It is
clearly labeled in the generation metadata (``provider: "mock"``) and is
intended for tests and demonstrations only; the application never silently
uses it when the real provider is requested.

Determinism: identical targets produce byte-identical strategies.
"""

from typing import List

from app.context.models import IssueContext
from app.core.config import Settings
from app.strategies.models import (
    CandidateStrategy,
    EffortRating,
    ImpactRating,
    StrategyGenerationRequest,
    StrategyType,
)


class MockStrategyProvider:
    """Context-aware deterministic provider (tests/demos only)."""

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(
        self, request: StrategyGenerationRequest
    ) -> List[CandidateStrategy]:
        target = request.target
        primary = target.issues[0] if target.issues else None
        count = request.strategy_count
        templates = _build_templates(primary, target)
        raw = [t for t in templates[:count]]
        return [CandidateStrategy.model_validate(item) for item in raw]


def _build_templates(
    issue: "IssueContext | None", target: object
) -> List[dict]:
    """Build up to five distinct, context-derived strategy dicts."""
    if issue is None:
        return [_empty_strategy(1, StrategyType.OTHER), _empty_strategy(2, StrategyType.OTHER)]

    rule_id = issue.rule.rule_id
    rule_name = issue.rule.rule_name or rule_id
    selector = issue.element.selector or "the affected element"
    criteria = issue.wcag.criteria or []
    # Group-level generation references the group; issue-level the issue.
    evidence = getattr(target, "group_id", None) or issue.issue_id

    def base(index: int) -> dict:
        return {
            "strategy_id": f"mock-strategy-{index}",
            "strategy_index": index,
            "issue_id": issue.issue_id,
            "group_id": getattr(target, "group_id", None),
            "context_version": "1.0",
            "wcag_alignment": list(criteria),
            "evidence_reference": evidence,
        }

    return [
        {
            **base(1),
            "strategy_type": StrategyType.NATIVE_HTML.value,
            "title": f"Fix '{rule_id}' with native semantic HTML",
            "summary": (
                f"Replace or augment the markup for {selector} with a native "
                f"HTML construct that satisfies the '{rule_id}' rule without "
                "ARIA. Native semantics are preferred because they are free, "
                "robust and work with assistive technology by default."
            ),
            "rationale": (
                f"The affected element ({issue.element.tag or 'unknown tag'}) "
                f"violates '{rule_id}' ({rule_name}). Native HTML semantics "
                f"are the lowest-risk fix because they are natively exposed "
                f"to the accessibility tree. WCAG alignment: "
                f"{', '.join(criteria) or 'as reported by axe'}."
            ),
            "implementation_steps": [
                f"Locate {selector} in the source markup.",
                "Replace the non-semantic construct with the equivalent native HTML element.",
                "Remove any redundant ARIA attributes that the native element now provides.",
                f"Re-run the scanner and confirm '{rule_id}' no longer fires.",
            ],
            "expected_accessibility_impact": ImpactRating.HIGH.value,
            "implementation_effort": EffortRating.LOW.value,
            "maintainability_notes": (
                "Native HTML is the most maintainable option — no custom "
                "attributes to keep in sync with behavior."
            ),
            "compatibility_notes": (
                "Broadly compatible across browsers and assistive technology."
            ),
            "risks": [
                "Native element may change default styling; verify visual layout.",
            ],
            "assumptions": [
                "The page source is editable and the element is not injected at runtime.",
            ],
            "confidence": 0.9,
        },
        {
            **base(2),
            "strategy_type": StrategyType.STRUCTURAL.value,
            "title": f"Restructure the surrounding markup for '{rule_id}'",
            "summary": (
                f"Adjust the DOM structure around {selector} so the affected "
                "element gains the context (label, heading order, grouping) "
                "it currently lacks, addressing the rule at the document "
                "structure level."
            ),
            "rationale": (
                f"The failure summary for '{rule_id}' indicates the element "
                "lacks the surrounding structure expected by the rule. "
                "Restructuring often fixes every occurrence of the same rule "
                "in one change, which is more maintainable than per-element "
                "patches."
            ),
            "implementation_steps": [
                f"Identify all occurrences of '{rule_id}' (see the scan's same-rule group).",
                "Add the missing structural wrapper or landmark to provide the expected context.",
                "Keep the change localized to the template or component that renders this element.",
                "Verify the accessibility tree exposes the expected name or relationship.",
                f"Re-run the scanner and confirm '{rule_id}' is resolved across occurrences.",
            ],
            "expected_accessibility_impact": ImpactRating.HIGH.value,
            "implementation_effort": EffortRating.MEDIUM.value,
            "maintainability_notes": (
                "Fixing the shared structure fixes all occurrences at once, "
                "but touching shared templates can affect other pages."
            ),
            "compatibility_notes": (
                "Structural HTML is fully supported; verify no layout regression."
            ),
            "risks": [
                "Shared template changes may affect unrelated pages.",
                "CSS selectors tied to the old structure may need updating.",
            ],
            "assumptions": [
                "The element is rendered by a shared, editable component.",
            ],
            "confidence": 0.7,
        },
        {
            **base(3),
            "strategy_type": StrategyType.ARIA.value,
            "title": f"Apply targeted ARIA only if native HTML cannot be used",
            "summary": (
                f"Use ARIA attributes (e.g. aria-labelledby) to expose the "
                f"required relationship for {selector} and satisfy the "
                f"'{rule_id}' rule — justified only when native HTML is "
                "genuinely unsuitable in this context."
            ),
            "rationale": (
                "ARIA is a fallback, not a first choice: it does not change "
                "behavior and can mask the underlying issue. It is proposed "
                f"for '{rule_id}' only because the existing DOM "
                "(runtime-generated content or a fixed component contract) "
                "may make the native alternative impractical. WCAG "
                f"alignment: {', '.join(criteria) or 'as reported by axe'}."
            ),
            "implementation_steps": [
                f"Confirm native HTML is not viable for {selector} (document the reason).",
                "Add the minimal ARIA attribute that exposes the missing relationship.",
                "Reference an existing element id rather than introducing new visible text where possible.",
                "Test with a screen reader, not just automated checks.",
            ],
            "expected_accessibility_impact": ImpactRating.MEDIUM.value,
            "implementation_effort": EffortRating.MEDIUM.value,
            "maintainability_notes": (
                "ARIA is a maintenance burden: it must stay in sync with "
                "behavior and is invisible to sighted users."
            ),
            "compatibility_notes": (
                "ARIA support varies; prefer well-supported attributes and "
                "verify with the target assistive technology."
            ),
            "risks": [
                "Overriding or misapplying ARIA can make the experience worse.",
                "ARIA does not fix the underlying semantic gap.",
            ],
            "assumptions": [
                "The DOM cannot be restructured natively in this component.",
            ],
            "confidence": 0.5,
        },
        {
            **base(4),
            "strategy_type": StrategyType.CONTENT.value,
            "title": f"Provide accessible content for '{rule_id}'",
            "summary": (
                f"Supply the text content (label, alternative text, or "
                f"instruction) that the element {selector} is missing, so the "
                "rule's content requirement is met directly."
            ),
            "rationale": (
                f"The '{rule_id}' rule commonly fails because content that "
                "should accompany the element is absent. Adding accurate, "
                "concise content is often the smallest change that satisfies "
                "the WCAG requirement without markup surgery."
            ),
            "implementation_steps": [
                f"Review the text currently visible near {selector}.",
                "Add the missing content (e.g. a label or alternative description).",
                "Keep the wording accurate and consistent with the page's tone.",
                "Verify the content is programmatically associated with the element.",
                f"Re-run the scanner and confirm '{rule_id}' no longer fires.",
            ],
            "expected_accessibility_impact": ImpactRating.MEDIUM.value,
            "implementation_effort": EffortRating.LOW.value,
            "maintainability_notes": (
                "Content changes are easy to review and maintain, but may "
                "need copy approval."
            ),
            "compatibility_notes": ("No compatibility risk from content-only changes."),
            "risks": [
                "Vague or duplicate content can create new confusion.",
            ],
            "assumptions": [
                "The correct content wording can be determined from the page.",
            ],
            "confidence": 0.8,
        },
        {
            **base(5),
            "strategy_type": StrategyType.BEHAVIORAL.value,
            "title": f"Fix interaction behavior for '{rule_id}'",
            "summary": (
                f"Adjust the interaction behavior associated with {selector} "
                "so the element is operable via keyboard or exposes its "
                "dynamic state, satisfying the rule's behavioral requirement."
            ),
            "rationale": (
                "Some rules fail at the behavior layer: keyboard handlers, "
                "focus management, or live-region announcements. Addressing "
                "behavior rather than markup alone fixes the underlying "
                "operability problem the rule flags."
            ),
            "implementation_steps": [
                f"Reproduce the interaction on {selector} with keyboard only.",
                "Add the missing keyboard handler or focus behavior.",
                "Announce dynamic changes via a live region where required.",
                "Verify with keyboard and a screen reader.",
                f"Re-run the scanner and confirm '{rule_id}' no longer fires.",
            ],
            "expected_accessibility_impact": ImpactRating.HIGH.value,
            "implementation_effort": EffortRating.HIGH.value,
            "maintainability_notes": (
                "Behavioral fixes touch JavaScript; keep the logic in the "
                "component and cover it with tests."
            ),
            "compatibility_notes": (
                "Keyboard and ARIA live-region behavior varies; test across "
                "browsers."
            ),
            "risks": [
                "Behavior changes can introduce regressions in other flows.",
            ],
            "assumptions": [
                "The page's JavaScript is editable and testable.",
            ],
            "confidence": 0.6,
        },
    ]


def _empty_strategy(index: int, strategy_type: StrategyType) -> dict:
    """Fallback used only when no issue evidence exists (should not happen)."""
    return {
        "strategy_id": f"mock-strategy-{index}",
        "strategy_index": index,
        "issue_id": "",
        "context_version": "1.0",
        "strategy_type": strategy_type.value,
        "title": f"Candidate strategy {index}",
        "summary": "No issue evidence was supplied to this provider.",
        "rationale": "No issue evidence was supplied to this provider.",
        "implementation_steps": ["Re-run generation with a resolved issue target."],
        "expected_accessibility_impact": ImpactRating.LOW.value,
        "implementation_effort": EffortRating.LOW.value,
        "maintainability_notes": "",
        "compatibility_notes": "",
        "risks": [],
        "assumptions": [],
        "confidence": 0.1,
        "evidence_reference": "",
    }
