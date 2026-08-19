"""Tests for the ranking algorithms (Module 6).

Covers weighted scoring, context factor detection, contextual weight
adjustment, explanation generation, tie handling, determinism, and edge
cases. All tests use deterministic data — no LLM, no network.
"""

import pytest

from app.context.models import (
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
from app.evaluations.models import StrategyEvaluation
from app.rankings.algorithms import (
    DEFAULT_WEIGHTS,
    apply_contextual_weights,
    compute_weighted_score,
    detect_context_factors,
    generate_explanation,
    rank_strategies,
    validate_weights,
)
from app.rankings.exceptions import RankingInvalidConfigError
from app.rankings.models import (
    ContextFactor,
    RankingMode,
    RankingWeights,
    RankedStrategy,
    RANKING_DIMENSIONS,
)
from app.scanners.models import Impact, WcagLevel


def _make_evaluation(
    strategy_id: str = "s-1",
    *,
    accessibility_impact_score: int = 7,
    standards_compliance_score: int = 8,
    contextual_suitability_score: int = 7,
    implementation_effort_score: int = 6,
    maintainability_score: int = 7,
    compatibility_score: int = 8,
    risk_score: int = 7,
) -> StrategyEvaluation:
    """A valid StrategyEvaluation with configurable scores."""
    return StrategyEvaluation(
        evaluation_id=f"eval-{strategy_id}",
        strategy_id=strategy_id,
        scan_id="scan-1",
        issue_id="issue-1",
        context_version="1.0",
        evaluator_provider="mock",
        evaluator_model="mock-model",
        prompt_version="1.0",
        accessibility_impact_score=accessibility_impact_score,
        standards_compliance_score=standards_compliance_score,
        contextual_suitability_score=contextual_suitability_score,
        implementation_effort_score=implementation_effort_score,
        maintainability_score=maintainability_score,
        compatibility_score=compatibility_score,
        risk_score=risk_score,
        strengths=["A strength."],
        weaknesses=["A weakness."],
        rationale="A rationale.",
    )


def _make_context(
    *,
    total_issues: int = 5,
    critical_count: int = 1,
    serious_count: int = 1,
    accessibility_score: float = 75.0,
) -> ContextDocument:
    """A minimal ContextDocument for testing."""
    return ContextDocument(
        project=ProjectContext(
            project_id="proj-1",
            name="Test Project",
            website_url="https://example.com",
            status="SCANNED",
        ),
        scan=ScanContext(
            scan_id="scan-1",
            project_id="proj-1",
            scanner_type="AXE",
            status="COMPLETED",
            total_issues=total_issues,
            critical_count=critical_count,
            serious_count=serious_count,
            accessibility_score=accessibility_score,
        ),
        page=PageContext(
            url="https://example.com",
            hostname="example.com",
            pathname="/",
            total_issues=total_issues,
            critical_count=critical_count,
            serious_count=serious_count,
            accessibility_score=accessibility_score,
        ),
        issues=[
            IssueContext(
                issue_id="issue-1",
                scan_id="scan-1",
                project_id="proj-1",
                rule=RuleContext(
                    rule_id="color-contrast",
                    rule_name="Color contrast",
                    impact=Impact.SERIOUS,
                ),
                impact=Impact.SERIOUS,
                wcag=WcagContext(
                    level=WcagLevel.AA,
                    criteria=["1.4.3"],
                    principle="Perceivable",
                ),
                element=ElementContext(
                    html='<p class="muted">Low contrast</p>',
                    tag="p",
                    selector="#main > p",
                    dom_path="html > body > main > p",
                ),
                evidence=EvidenceContext(failure_summary="Insufficient contrast."),
            ),
        ],
        groups=[
            IssueGroup(
                group_id="rule:color-contrast",
                group_type="same_rule",
                label="Color contrast issues",
                issue_ids=["issue-1"],
            ),
        ],
    )


# --- validate_weights -------------------------------------------------------

def test_validate_weights_accepts_1_0() -> None:
    """Weights summing to 1.0 are accepted."""
    validate_weights(DEFAULT_WEIGHTS)  # should not raise


def test_validate_weights_rejects_bad_sum() -> None:
    """Weights not summing to 1.0 raise RankingInvalidConfigError."""
    bad = RankingWeights(
        accessibility_impact=0.5,
        standards_compliance=0.5,
        contextual_suitability=0.5,
        implementation_effort=0.5,
        maintainability=0.5,
        compatibility=0.5,
        risk=0.5,
    )
    with pytest.raises(RankingInvalidConfigError):
        validate_weights(bad)


# --- compute_weighted_score -------------------------------------------------

def test_weighted_score_equal_weights() -> None:
    """With equal weights, the weighted score is the arithmetic mean."""
    eval_ = _make_evaluation(
        accessibility_impact_score=8,
        standards_compliance_score=6,
        contextual_suitability_score=10,
        implementation_effort_score=4,
        maintainability_score=8,
        compatibility_score=6,
        risk_score=10,
    )
    score = compute_weighted_score(eval_, DEFAULT_WEIGHTS)
    expected = (8 + 6 + 10 + 4 + 8 + 6 + 10) / 7
    assert abs(score - expected) < 0.01


def test_weighted_score_custom_weights() -> None:
    """Custom weights produce the expected weighted sum."""
    eval_ = _make_evaluation(
        accessibility_impact_score=10,
        standards_compliance_score=0,
        contextual_suitability_score=0,
        implementation_effort_score=0,
        maintainability_score=0,
        compatibility_score=0,
        risk_score=0,
    )
    weights = RankingWeights(
        accessibility_impact=1.0,
        standards_compliance=0.0,
        contextual_suitability=0.0,
        implementation_effort=0.0,
        maintainability=0.0,
        compatibility=0.0,
        risk=0.0,
    )
    score = compute_weighted_score(eval_, weights)
    assert abs(score - 10.0) < 0.01


def test_weighted_score_zero_all() -> None:
    """All-zero evaluations produce a zero weighted score."""
    eval_ = _make_evaluation(
        accessibility_impact_score=0,
        standards_compliance_score=0,
        contextual_suitability_score=0,
        implementation_effort_score=0,
        maintainability_score=0,
        compatibility_score=0,
        risk_score=0,
    )
    score = compute_weighted_score(eval_, DEFAULT_WEIGHTS)
    assert score == 0.0


def test_weighted_score_max_all() -> None:
    """All-ten evaluations produce a weighted score of 10.0."""
    eval_ = _make_evaluation(
        accessibility_impact_score=10,
        standards_compliance_score=10,
        contextual_suitability_score=10,
        implementation_effort_score=10,
        maintainability_score=10,
        compatibility_score=10,
        risk_score=10,
    )
    score = compute_weighted_score(eval_, DEFAULT_WEIGHTS)
    assert abs(score - 10.0) < 0.01


# --- detect_context_factors -------------------------------------------------

def test_detect_critical_issue_factor() -> None:
    """Critical/serious issues trigger the critical_wcag_issue factor."""
    context = _make_context()
    issue = context.issues[0]  # Impact.SERIOUS
    factors = detect_context_factors(context, issue)
    critical = next(f for f in factors if f.factor == "critical_wcag_issue")
    assert critical.detected is True
    assert critical.influence > 0


def test_detect_non_critical_issue() -> None:
    """Minor issues do not trigger the critical factor."""
    context = _make_context()
    issue = IssueContext(
        issue_id="issue-minor",
        scan_id="scan-1",
        project_id="proj-1",
        rule=RuleContext(
            rule_id="link-name",
            rule_name="Links must have discernible text",
            impact=Impact.MINOR,
        ),
        impact=Impact.MINOR,
    )
    factors = detect_context_factors(context, issue)
    critical = next(f for f in factors if f.factor == "critical_wcag_issue")
    assert critical.detected is False
    assert critical.influence == 0.0


def test_detect_high_issue_frequency() -> None:
    """More than 10 issues triggers high_issue_frequency."""
    context = _make_context(total_issues=15)
    issue = context.issues[0]
    factors = detect_context_factors(context, issue)
    freq = next(f for f in factors if f.factor == "high_issue_frequency")
    assert freq.detected is True


def test_detect_low_accessibility_score() -> None:
    """Score below 60 triggers low_accessibility_score."""
    context = _make_context(accessibility_score=45.0)
    issue = context.issues[0]
    factors = detect_context_factors(context, issue)
    low = next(f for f in factors if f.factor == "low_accessibility_score")
    assert low.detected is True


def test_detect_multiple_severe_issues() -> None:
    """More than 3 critical+serious triggers multiple_severe_issues."""
    context = _make_context(critical_count=2, serious_count=3)
    issue = context.issues[0]
    factors = detect_context_factors(context, issue)
    severe = next(f for f in factors if f.factor == "multiple_severe_issues")
    assert severe.detected is True


def test_all_factors_detected_flag() -> None:
    """Every factor has a detected boolean."""
    context = _make_context()
    issue = context.issues[0]
    factors = detect_context_factors(context, issue)
    assert all(isinstance(f.detected, bool) for f in factors)
    assert len(factors) >= 5  # at least 5 factors defined


# --- apply_contextual_weights -----------------------------------------------

def test_baseline_unchanged() -> None:
    """When no factors are detected, contextual weights equal baseline."""
    base = DEFAULT_WEIGHTS
    no_factors = [
        ContextFactor(
            factor="test",
            detected=False,
            influence=0.0,
            affected_dimensions=["risk"],
            explanation="Not detected.",
        )
    ]
    result = apply_contextual_weights(base, no_factors)
    assert abs(result.total() - 1.0) < 0.001
    for dim in RANKING_DIMENSIONS:
        assert abs(getattr(result, dim) - getattr(base, dim)) < 0.001


def test_contextual_weights_renormalized() -> None:
    """After adjustment, weights always sum to 1.0."""
    base = DEFAULT_WEIGHTS
    factors = [
        ContextFactor(
            factor="critical_wcag_issue",
            detected=True,
            influence=0.5,
            affected_dimensions=["accessibility_impact", "standards_compliance"],
            explanation="Critical issue detected.",
        ),
    ]
    result = apply_contextual_weights(base, factors)
    assert abs(result.total() - 1.0) < 0.001


def test_contextual_weights_adjust_direction() -> None:
    """Detected factors increase the weight of affected dimensions."""
    base = DEFAULT_WEIGHTS
    original_accessibility = base.accessibility_impact
    factors = [
        ContextFactor(
            factor="critical_wcag_issue",
            detected=True,
            influence=0.5,
            affected_dimensions=["accessibility_impact"],
            explanation="Critical issue.",
        ),
    ]
    result = apply_contextual_weights(base, factors)
    assert result.accessibility_impact > original_accessibility


# --- rank_strategies --------------------------------------------------------

def test_ranking_order() -> None:
    """Strategies are ranked by weighted score descending."""
    evals = [
        _make_evaluation("s-low", accessibility_impact_score=3, risk_score=3),
        _make_evaluation("s-high", accessibility_impact_score=9, risk_score=9),
        _make_evaluation("s-mid", accessibility_impact_score=6, risk_score=6),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert [r.strategy_id for r in ranked] == ["s-high", "s-mid", "s-low"]
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_ranking_tie_breaking() -> None:
    """Ties are broken by strategy_id alphabetically."""
    evals = [
        _make_evaluation("s-b", accessibility_impact_score=5),
        _make_evaluation("s-a", accessibility_impact_score=5),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert ranked[0].strategy_id == "s-a"
    assert ranked[1].strategy_id == "s-b"


def test_ranking_deterministic() -> None:
    """Identical inputs produce identical rankings."""
    evals = [
        _make_evaluation("s-1", accessibility_impact_score=8),
        _make_evaluation("s-2", accessibility_impact_score=6),
    ]
    first = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    second = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert [r.strategy_id for r in first] == [r.strategy_id for r in second]
    assert [r.weighted_score for r in first] == [r.weighted_score for r in second]


def test_ranking_single_strategy() -> None:
    """A single strategy gets rank 1."""
    evals = [_make_evaluation("s-1")]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert len(ranked) == 1
    assert ranked[0].rank == 1


def test_ranking_with_context_factors() -> None:
    """Context factors are passed through to the ranking."""
    evals = [
        _make_evaluation("s-1", accessibility_impact_score=9),
        _make_evaluation("s-2", accessibility_impact_score=5),
    ]
    factors = [
        ContextFactor(
            factor="critical_wcag_issue",
            detected=True,
            influence=0.3,
            affected_dimensions=["accessibility_impact"],
            explanation="Critical.",
        ),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, factors, "contextual")
    assert ranked[0].strategy_id == "s-1"
    assert ranked[0].rank == 1


def test_ranked_strategy_has_explanation() -> None:
    """Every ranked strategy has a non-empty explanation."""
    evals = [
        _make_evaluation("s-1", accessibility_impact_score=8),
        _make_evaluation("s-2", accessibility_impact_score=5),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    for r in ranked:
        assert r.ranking_explanation
        assert len(r.ranking_explanation) > 10


def test_ranked_strategy_has_dimension_scores() -> None:
    """Every ranked strategy has all seven dimension scores."""
    evals = [_make_evaluation("s-1")]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert len(ranked) == 1
    for dim in RANKING_DIMENSIONS:
        assert dim in ranked[0].dimension_scores


def test_ranked_strategy_strengths_weaknesses() -> None:
    """Ranked strategies carry strengths and weaknesses from evaluations."""
    evals = [_make_evaluation("s-1")]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert ranked[0].strengths
    assert ranked[0].weaknesses


# --- generate_explanation ---------------------------------------------------

def test_generate_explanation_mentions_dimensions() -> None:
    """The explanation mentions top contributing dimensions."""
    evals = [_make_evaluation("s-1", accessibility_impact_score=10)]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    explanation = ranked[0].ranking_explanation
    assert "accessibility impact" in explanation.lower()


def test_generate_explanation_mentions_factors() -> None:
    """The explanation mentions detected context factors."""
    evals = [_make_evaluation("s-1")]
    factors = [
        ContextFactor(
            factor="critical_wcag_issue",
            detected=True,
            influence=0.3,
            affected_dimensions=["accessibility_impact"],
            explanation="Critical.",
        ),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, factors, "contextual")
    explanation = ranked[0].ranking_explanation
    assert "critical_wcag_issue" in explanation.replace("_", " ") or "critical wcag issue" in explanation.lower() or "critical" in explanation.lower()


# --- edge cases -------------------------------------------------------------

def test_all_same_scores() -> None:
    """When all strategies have the same scores, ranking is by strategy_id."""
    evals = [
        _make_evaluation("s-c"),
        _make_evaluation("s-a"),
        _make_evaluation("s-b"),
    ]
    ranked = rank_strategies(evals, DEFAULT_WEIGHTS, [], "baseline")
    assert [r.strategy_id for r in ranked] == ["s-a", "s-b", "s-c"]


def test_weights_extreme_values() -> None:
    """Weights with extreme values (one dimension dominant) work correctly."""
    evals = [
        _make_evaluation("s-1", accessibility_impact_score=10, risk_score=0),
        _make_evaluation("s-2", accessibility_impact_score=0, risk_score=10),
    ]
    weights_all_access = RankingWeights(
        accessibility_impact=1.0,
        standards_compliance=0.0,
        contextual_suitability=0.0,
        implementation_effort=0.0,
        maintainability=0.0,
        compatibility=0.0,
        risk=0.0,
    )
    ranked = rank_strategies(evals, weights_all_access, [], "baseline")
    assert ranked[0].strategy_id == "s-1"  # high accessibility wins

    weights_all_risk = RankingWeights(
        accessibility_impact=0.0,
        standards_compliance=0.0,
        contextual_suitability=0.0,
        implementation_effort=0.0,
        maintainability=0.0,
        compatibility=0.0,
        risk=1.0,
    )
    ranked = rank_strategies(evals, weights_all_risk, [], "baseline")
    assert ranked[0].strategy_id == "s-2"  # low risk wins
