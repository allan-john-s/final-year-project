"""Deterministic mock evaluation provider.

Evaluates a candidate strategy against the *actual* issue context (rule,
WCAG criteria, element evidence) with a fixed, per-strategy-type score table
and context-referencing qualitative reasoning. No LLM is involved, scores are
never random, and identical inputs produce byte-identical evaluations — the
provider is clearly labeled (``provider: \"mock\"``) and intended for tests
and demonstrations only.

Score semantics follow the domain model: positive criteria 10 = excellent;
implementation effort 10 = very easy; risk 10 = very low risk.
"""

from typing import List, Tuple

from app.core.config import Settings
from app.evaluations.exceptions import EvaluationOutputError
from app.evaluations.models import (
    EVALUATION_VERSION,
    EvaluationDraft,
    StrategyEvaluationRequest,
)
from app.strategies.models import StrategyType

# (accessibility_impact, standards, contextual_suitability, effort,
#  maintainability, compatibility, risk) — fixed per strategy family.
_SCORES: dict = {
    StrategyType.NATIVE_HTML: (9, 9, 8, 8, 9, 9, 8),
    StrategyType.STRUCTURAL: (9, 8, 8, 5, 7, 8, 6),
    StrategyType.ARIA: (6, 7, 6, 5, 5, 6, 5),
    StrategyType.CONTENT: (7, 8, 8, 9, 8, 9, 8),
    StrategyType.BEHAVIORAL: (9, 8, 8, 4, 6, 7, 5),
    StrategyType.VISUAL: (6, 7, 7, 6, 7, 8, 7),
    StrategyType.ALTERNATIVE: (6, 7, 7, 7, 7, 8, 7),
    StrategyType.OTHER: (5, 5, 5, 5, 5, 6, 6),
}

_FALLBACK = _SCORES[StrategyType.OTHER]


class MockEvaluationProvider:
    """Deterministic, context-aware evaluator (tests/demos only)."""

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def evaluate(
        self, request: StrategyEvaluationRequest
    ) -> EvaluationDraft:
        strategy = request.strategy
        issue = request.target.issues[0] if request.target.issues else None
        if issue is None:
            raise EvaluationOutputError(
                "The mock evaluator requires issue evidence for the target."
            )
        return _build_draft(strategy, issue)


def _build_draft(strategy, issue) -> EvaluationDraft:
    """Deterministic draft derived from the strategy type + issue evidence."""
    scores = _SCORES.get(strategy.strategy_type, _FALLBACK)
    rule_id = issue.rule.rule_id
    rule_name = issue.rule.rule_name or rule_id
    selector = issue.element.selector or "the affected element"
    criteria = issue.wcag.criteria or []
    reference = strategy.evidence_reference or issue.issue_id

    # One small deterministic contextual adjustment: ARIA is more suitable
    # when the element already carries ARIA attributes or a role.
    contextual = scores[2]
    if strategy.strategy_type is StrategyType.ARIA:
        if issue.element.aria or issue.element.role:
            contextual = min(10, contextual + 1)

    accessibility, standards, effort, maintainability, compatibility, risk = (
        scores[0],
        scores[1],
        scores[3],
        scores[4],
        scores[5],
        scores[6],
    )

    strengths, weaknesses, rationale = _reasoning(
        strategy, issue, rule_id, rule_name, selector, criteria
    )

    return EvaluationDraft(
        strategy_id=strategy.strategy_id,
        accessibility_impact_score=accessibility,
        standards_compliance_score=standards,
        contextual_suitability_score=contextual,
        implementation_effort_score=effort,
        maintainability_score=maintainability,
        compatibility_score=compatibility,
        risk_score=risk,
        strengths=strengths,
        weaknesses=weaknesses,
        rationale=rationale,
        assumptions=list(strategy.assumptions),
        uncertainties=[
            "Automated evaluation cannot verify real-world assistive technology "
            "behavior; a manual screen-reader check is still required."
        ],
        evidence_references=[reference] if reference else [issue.issue_id],
    )


def _reasoning(
    strategy, issue, rule_id: str, rule_name: str, selector: str, criteria: List[str]
) -> Tuple[List[str], List[str], str]:
    """Deterministic strengths/weaknesses/rationale referencing the evidence."""
    wcag_text = ", ".join(criteria) or "as reported by axe"

    if strategy.strategy_type is StrategyType.NATIVE_HTML:
        strengths = [
            f"Directly addresses '{rule_id}' ({rule_name}) on {selector} using "
            "a native semantic HTML construct, which is exposed to assistive "
            "technology by default.",
            "No ARIA maintenance burden: the fix lives in plain markup and "
            "stays in sync automatically.",
            f"Native semantics align with WCAG {wcag_text} without custom "
            "attributes.",
        ]
        weaknesses = [
            "A native element can change default rendering; visual regression "
            f"checks for {selector} are required.",
            "The fix only works where the underlying DOM can actually be "
            "restructured.",
        ]
        rationale = (
            f"This {strategy.strategy_type.value} strategy is rated highest on "
            "accessibility impact and maintainability because native semantics "
            f"are the most robust way to satisfy '{rule_id}' on {selector} "
            f"(WCAG {wcag_text}). Implementation effort is low when the "
            "markup is editable, and compatibility is broad. The main "
            "weakness is visual regression risk from the element swap."
        )
    elif strategy.strategy_type is StrategyType.STRUCTURAL:
        strengths = [
            f"Fixing the surrounding structure can resolve every occurrence of "
            f"'{rule_id}' in one change, not just the instance at {selector}.",
            "Addresses the root cause at the document/component level.",
            f"Structural HTML keeps WCAG {wcag_text} compliance without ARIA.",
        ]
        weaknesses = [
            f"Touching shared structure near {selector} can affect unrelated "
            "pages or components.",
            "Higher coordination effort: CSS selectors and templates tied to "
            "the old structure may need updating.",
        ]
        rationale = (
            f"Restructuring around {selector} targets the shared cause of "
            f"'{rule_id}' and scores well on accessibility impact, but the "
            "implementation effort is higher because the change is broader "
            "than a single-element patch. Regression risk to unrelated "
            "content is the main uncertainty."
        )
    elif strategy.strategy_type is StrategyType.ARIA:
        strengths = [
            f"ARIA can expose the missing relationship for '{rule_id}' at "
            f"{selector} where the DOM cannot be restructured natively.",
            "Suitable when the element is runtime-generated or governed by a "
            "fixed component contract.",
        ]
        weaknesses = [
            "ARIA does not change behavior and can mask the underlying "
            f"semantic gap behind '{rule_id}'.",
            "ARIA must be kept in sync manually and is invisible to sighted "
            "users — a long-term maintenance burden.",
            "Assistive-technology support for the specific attribute must be "
            "verified, since automated checks cannot confirm real behavior.",
        ]
        rationale = (
            f"'{rule_id}' on {selector} is best fixed natively, so this ARIA "
            "strategy scores lower on accessibility impact and maintainability "
            "and is only contextually suitable when the DOM cannot be "
            "restructured (an assumption stated by the strategy). It is "
            "recommended only as a fallback; WCAG "
            f"{wcag_text} still applies and must be verified manually."
        )
    elif strategy.strategy_type is StrategyType.CONTENT:
        strengths = [
            f"Supplying the missing content for '{rule_id}' at {selector} is "
            "often the smallest, lowest-risk change.",
            "Content-only changes carry no markup or behavior compatibility "
            "risk.",
            f"Directly satisfies the WCAG {wcag_text} content requirement.",
        ]
        weaknesses = [
            "Correct wording must be determined from the page; vague or "
            "duplicate content can create new confusion.",
            "May require copy approval, which can slow the change.",
        ]
        rationale = (
            f"The '{rule_id}' failure at {selector} is frequently a content "
            "gap, so this strategy rates highest on implementation effort "
            "(easy) and compatibility. Accessibility impact is solid but "
            "depends on the accuracy of the added content, which is the "
            "stated uncertainty."
        )
    elif strategy.strategy_type is StrategyType.BEHAVIORAL:
        strengths = [
            f"Addresses the operability root cause behind '{rule_id}' at "
            f"{selector} (keyboard, focus, live regions) rather than patching "
            "markup.",
            "High accessibility impact when the failure is behavioral.",
        ]
        weaknesses = [
            "Behavioral changes touch JavaScript and carry regression risk "
            "for other flows.",
            "Keyboard and live-region behavior varies across browsers and "
            "assistive technology; testing effort is significant.",
        ]
        rationale = (
            f"'{rule_id}' on {selector} has a behavioral component, so this "
            "strategy can have high accessibility impact. However, "
            "implementation effort is the highest of the alternatives and "
            "cross-browser verification is required, which lowers its "
            "maintainability and risk scores."
        )
    elif strategy.strategy_type is StrategyType.VISUAL:
        strengths = [
            f"Adjusting presentation for '{rule_id}' at {selector} can meet "
            "visual WCAG requirements (e.g. contrast) without markup changes.",
        ]
        weaknesses = [
            "Visual-only changes may not address the underlying semantic "
            "cause of the rule failure.",
            "Requires design review and can be subjective.",
        ]
        rationale = (
            f"This visual strategy for '{rule_id}' on {selector} is moderate "
            "across most dimensions: low implementation effort but weaker "
            "guarantees on the underlying accessibility requirement."
        )
    else:
        strengths = [
            f"Provides an alternative remediation path for '{rule_id}' at "
            f"{selector}.",
        ]
        weaknesses = [
            "Alternative approaches have less evidence of satisfying the "
            "rule; manual verification is required.",
        ]
        rationale = (
            f"This alternative strategy for '{rule_id}' on {selector} is "
            "rated moderate across dimensions because its effectiveness "
            "depends on context that automated evaluation cannot fully "
            "confirm."
        )

    return strengths, weaknesses, rationale
