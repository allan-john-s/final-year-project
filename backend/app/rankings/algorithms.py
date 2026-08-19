"""Ranking algorithms (Module 6).

Transparent, deterministic, fully testable ranking algorithms that combine
the seven Module 5 evaluation dimensions using configurable weights.

All algorithms are pure functions — no state, no LLM calls, no network.
The contextual weighting logic derives exclusively from information present
in the ContextDocument; no factors are invented.

Score direction
---------------
All seven dimensions use the same direction: higher is better.

- accessibility_impact_score: 10 = excellent
- standards_compliance_score: 10 = excellent
- contextual_suitability_score: 10 = excellent
- implementation_effort_score: 10 = very easy / very low effort
- maintainability_score: 10 = excellent
- compatibility_score: 10 = excellent
- risk_score: 10 = very low risk

Because all seven share the same direction, the weighted sum requires
no inversions.
"""

from typing import List, Tuple

from app.context.models import ContextDocument, IssueContext, IssueGroup
from app.evaluations.models import StrategyEvaluation
from app.rankings.models import (
    ContextFactor,
    RankingMode,
    RankingWeights,
    RankedStrategy,
    RANKING_DIMENSIONS,
)

# Default (baseline) weights — equal distribution across seven dimensions.
# Each weight = 1/7 ≈ 0.1429.
_DEFAULT_TOTAL = 7
DEFAULT_WEIGHTS = RankingWeights(
    accessibility_impact=1 / _DEFAULT_TOTAL,
    standards_compliance=1 / _DEFAULT_TOTAL,
    contextual_suitability=1 / _DEFAULT_TOTAL,
    implementation_effort=1 / _DEFAULT_TOTAL,
    maintainability=1 / _DEFAULT_TOTAL,
    compatibility=1 / _DEFAULT_TOTAL,
    risk=1 / _DEFAULT_TOTAL,
)
"""Baseline weights: equal distribution across all seven dimensions."""

# Tolerance for weight sum validation (floating-point).
_WEIGHT_TOLERANCE = 0.001


def validate_weights(weights: RankingWeights) -> None:
    """Validate that weights sum to approximately 1.0.

    :raises RankingInvalidConfigError: if weights are invalid.
    """
    total = weights.total()
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        from app.rankings.exceptions import RankingInvalidConfigError
        raise RankingInvalidConfigError(
            f"Weights must sum to 1.0 (±{_WEIGHT_TOLERANCE}), got {total:.6f}"
        )


def compute_weighted_score(
    evaluation: StrategyEvaluation,
    weights: RankingWeights,
) -> float:
    """Compute the weighted score for one evaluation.

    All seven dimensions use the same score direction (higher = better),
    so the weighted sum is a direct linear combination.

    :returns: weighted score in [0.0, 10.0].
    """
    score = (
        evaluation.accessibility_impact_score * weights.accessibility_impact
        + evaluation.standards_compliance_score * weights.standards_compliance
        + evaluation.contextual_suitability_score * weights.contextual_suitability
        + evaluation.implementation_effort_score * weights.implementation_effort
        + evaluation.maintainability_score * weights.maintainability
        + evaluation.compatibility_score * weights.compatibility
        + evaluation.risk_score * weights.risk
    )
    return round(score, 4)


def detect_context_factors(
    context: ContextDocument,
    target_issue: IssueContext,
) -> List[ContextFactor]:
    """Detect contextual factors from the ContextDocument.

    Every factor is derived exclusively from information present in the
    ContextDocument — no invented factors. The logic is fully deterministic
    and testable.

    :param context: the full context document.
    :param target_issue: the specific issue being ranked.
    :returns: list of detected contextual factors.
    """
    factors: List[ContextFactor] = []

    # Factor 1: Critical WCAG issue
    # If the issue has critical or serious impact, accessibility and
    # standards compliance should dominate the ranking.
    is_critical = target_issue.impact.value in ("CRITICAL", "SERIOUS")
    factors.append(ContextFactor(
        factor="critical_wcag_issue",
        detected=is_critical,
        influence=0.3 if is_critical else 0.0,
        affected_dimensions=["accessibility_impact", "standards_compliance"],
        explanation=(
            "The issue has critical or serious impact, so accessibility "
            "improvement and WCAG compliance are weighted more heavily."
            if is_critical
            else "The issue is not critical or serious, so accessibility "
            "and standards weights remain at baseline."
        ),
    ))

    # Factor 2: WCAG level A (most fundamental)
    is_level_a = (
        target_issue.wcag.level is not None
        and target_issue.wcag.level.value == "A"
    )
    factors.append(ContextFactor(
        factor="wcag_level_a",
        detected=is_level_a,
        influence=0.2 if is_level_a else 0.0,
        affected_dimensions=["standards_compliance", "accessibility_impact"],
        explanation=(
            "The issue violates a WCAG Level A criterion (most fundamental), "
            "so standards compliance and accessibility impact are prioritized."
            if is_level_a
            else "The issue does not violate a Level A criterion."
        ),
    ))

    # Factor 3: Complex DOM (deep nesting detected via dom_path)
    has_deep_dom = False
    if target_issue.element.dom_path:
        depth = target_issue.element.dom_path.count(" > ") + target_issue.element.dom_path.count(" >")
        has_deep_dom = depth > 5
    factors.append(ContextFactor(
        factor="complex_dom",
        detected=has_deep_dom,
        influence=0.2 if has_deep_dom else 0.0,
        affected_dimensions=["maintainability", "compatibility"],
        explanation=(
            "The affected element has a deep DOM nesting, suggesting complex "
            "structure. Maintainability and compatibility are weighted more "
            "heavily to avoid fragile fixes."
            if has_deep_dom
            else "The DOM nesting depth is within normal range."
        ),
    ))

    # Factor 4: High issue frequency (many issues in the scan)
    high_issue_frequency = context.scan.total_issues > 10
    factors.append(ContextFactor(
        factor="high_issue_frequency",
        detected=high_issue_frequency,
        influence=0.15 if high_issue_frequency else 0.0,
        affected_dimensions=["implementation_effort", "maintainability"],
        explanation=(
            f"The scan found {context.scan.total_issues} issues, suggesting "
            "systemic accessibility problems. Implementation effort and "
            "maintainability are weighted more heavily for scalable fixes."
            if high_issue_frequency
            else f"The scan found {context.scan.total_issues} issue(s), "
            "which is within normal range."
        ),
    ))

    # Factor 5: Multiple critical/serious issues
    multiple_severe = (
        context.scan.critical_count + context.scan.serious_count > 3
    )
    factors.append(ContextFactor(
        factor="multiple_severe_issues",
        detected=multiple_severe,
        influence=0.25 if multiple_severe else 0.0,
        affected_dimensions=["accessibility_impact", "standards_compliance"],
        explanation=(
            f"The scan has {context.scan.critical_count} critical and "
            f"{context.scan.serious_count} serious issues, indicating "
            "widespread severe accessibility problems. Accessibility impact "
            "and standards compliance are weighted more heavily."
            if multiple_severe
            else "The scan has few severe issues."
        ),
    ))

    # Factor 6: Low accessibility score
    low_score = (
        context.scan.accessibility_score is not None
        and context.scan.accessibility_score < 60
    )
    factors.append(ContextFactor(
        factor="low_accessibility_score",
        detected=low_score,
        influence=0.2 if low_score else 0.0,
        affected_dimensions=["accessibility_impact", "contextual_suitability"],
        explanation=(
            f"The accessibility score is {context.scan.accessibility_score}, "
            "which is below 60. High-impact fixes that are contextually "
            "suitable are prioritized."
            if low_score
            else "The accessibility score is within acceptable range."
        ),
    ))

    return factors


def apply_contextual_weights(
    base_weights: RankingWeights,
    factors: List[ContextFactor],
) -> RankingWeights:
    """Adjust baseline weights based on detected contextual factors.

    The adjustment is additive: each factor contributes an influence value
    to the affected dimensions. After adjustment, weights are re-normalized
    to sum to 1.0.

    :param base_weights: the baseline weights to adjust.
    :param factors: detected context factors.
    :returns: new weights that sum to 1.0.
    """
    # Start with a copy of the base weights as raw values.
    adjustments: dict = {dim: 0.0 for dim in RANKING_DIMENSIONS}

    for factor in factors:
        if not factor.detected:
            continue
        for dim in factor.affected_dimensions:
            if dim in adjustments:
                adjustments[dim] += factor.influence

    # Apply adjustments to base weights.
    adjusted: dict = {}
    for dim in RANKING_DIMENSIONS:
        base = getattr(base_weights, dim)
        adjusted[dim] = max(0.0, base + adjustments[dim])

    # Re-normalize to sum to 1.0.
    total = sum(adjusted.values())
    if total > 0:
        for dim in adjusted:
            adjusted[dim] = adjusted[dim] / total

    return RankingWeights(**adjusted)


def generate_explanation(
    ranked: RankedStrategy,
    strategy_index: int,
    weights: RankingWeights,
    factors: List[ContextFactor],
    total_strategies: int,
) -> str:
    """Generate a human-readable explanation for a ranked strategy.

    The explanation covers: why the strategy received its score, which
    dimensions contributed most, and which contextual factors affected
    the weights.

    :param ranked: the ranked strategy (with dimension_scores).
    :param strategy_index: the original strategy index (1-based).
    :param weights: the weights used for this ranking.
    :param factors: the context factors that were applied.
    :param total_strategies: total number of strategies ranked.
    :returns: a detailed explanation string.
    """
    # Find the top contributing dimensions (highest score × weight).
    contributions = []
    for dim in RANKING_DIMENSIONS:
        score = ranked.dimension_scores.get(dim, 0)
        weight = getattr(weights, dim)
        contributions.append((dim, score, weight, round(score * weight, 4)))
    contributions.sort(key=lambda x: x[3], reverse=True)

    dim_labels = {
        "accessibility_impact": "accessibility impact",
        "standards_compliance": "standards compliance",
        "contextual_suitability": "contextual suitability",
        "implementation_effort": "implementation effort",
        "maintainability": "maintainability",
        "compatibility": "compatibility",
        "risk": "risk",
    }

    # Top 3 contributing dimensions.
    top_dims = contributions[:3]
    top_parts = [f"{dim_labels[d]} ({s}/10 × {w:.2%} = {c:.2f})" for d, s, w, c in top_dims]

    parts = [
        f"Strategy #{strategy_index} ranked {ranked.rank}{'st' if ranked.rank == 1 else 'nd' if ranked.rank == 2 else 'rd' if ranked.rank == 3 else 'th'} "
        f"out of {total_strategies} with a weighted score of {ranked.weighted_score:.2f}/10.",
        f"The highest contributing dimensions were: {'; '.join(top_parts)}.",
    ]

    # Mention detected context factors.
    detected = [f for f in factors if f.detected]
    if detected:
        factor_names = [f.factor.replace("_", " ") for f in detected]
        parts.append(
            f"Context-aware factors influenced the ranking: {', '.join(factor_names)}."
        )

    if ranked.ranking_explanation:
        parts.append(ranked.ranking_explanation)

    return " ".join(parts)


def rank_strategies(
    evaluations: List[StrategyEvaluation],
    weights: RankingWeights,
    factors: List[ContextFactor],
    ranking_method: str,
) -> List[RankedStrategy]:
    """Rank strategies by their weighted scores.

    Strategies are sorted by weighted_score descending. Ties are broken
    by strategy_id alphabetically for determinism.

    :param evaluations: the evaluations to rank (one per strategy).
    :param weights: the weights to apply.
    :param factors: the context factors used.
    :param ranking_method: "baseline" or "contextual".
    :returns: list of RankedStrategy in descending order.
    """
    scored: List[Tuple[StrategyEvaluation, float]] = []
    for evaluation in evaluations:
        ws = compute_weighted_score(evaluation, weights)
        scored.append((evaluation, ws))

    # Sort by weighted_score descending, then by strategy_id ascending for ties.
    scored.sort(key=lambda x: (-x[1], x[0].strategy_id))

    ranked: List[RankedStrategy] = []
    for rank_pos, (evaluation, ws) in enumerate(scored, start=1):
        # Build dimension scores dict.
        dim_scores = {}
        for dim in RANKING_DIMENSIONS:
            field_name = f"{dim}_score"
            dim_scores[dim] = getattr(evaluation, field_name, 0)

        # Build top strengths and weaknesses from the evaluation.
        strengths = list(evaluation.strengths[:5])
        weaknesses = list(evaluation.weaknesses[:5])

        ranked_item = RankedStrategy(
            strategy_id=evaluation.strategy_id,
            rank=rank_pos,
            weighted_score=ws,
            dimension_scores=dim_scores,
            strengths=strengths,
            weaknesses=weaknesses,
            ranking_explanation="pending",  # filled below
            confidence=min(evaluation.accessibility_impact_score / 10.0, 1.0),
        )

        explanation = generate_explanation(
            ranked_item,
            strategy_index=rank_pos,
            weights=weights,
            factors=factors,
            total_strategies=len(scored),
        )
        ranked_item.ranking_explanation = explanation
        ranked.append(ranked_item)

    return ranked
