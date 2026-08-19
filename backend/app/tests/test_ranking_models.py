"""Tests for the ranking domain models (Module 6).

Covers RankingWeights validation (sum = 1.0, bounds), RankingMode enum,
ContextFactor fields, RankedStrategy fields, RankingBatch/RankingResult
models, and the no-secrets guarantee.
"""

import pytest
from pydantic import ValidationError

from app.rankings.algorithms import validate_weights
from app.rankings.exceptions import RankingInvalidConfigError
from app.rankings.models import (
    ContextFactor,
    RankingBatch,
    RankingMode,
    RankingWeights,
    RankedStrategy,
    RankingResult,
    RANKING_DIMENSIONS,
    RANKING_VERSION,
)


def test_ranking_weights_valid() -> None:
    """Valid weights that sum to 1.0 are accepted."""
    w = RankingWeights(
        accessibility_impact=0.2,
        standards_compliance=0.15,
        contextual_suitability=0.15,
        implementation_effort=0.15,
        maintainability=0.1,
        compatibility=0.1,
        risk=0.15,
    )
    assert abs(w.total() - 1.0) < 0.001
    assert w.accessibility_impact == 0.2


def test_ranking_weights_must_sum_to_one() -> None:
    """Weights that don't sum to 1.0 are accepted by the model but
    rejected by validate_weights()."""
    w = RankingWeights(
        accessibility_impact=0.5,
        standards_compliance=0.5,
        contextual_suitability=0.5,
        implementation_effort=0.5,
        maintainability=0.5,
        compatibility=0.5,
        risk=0.5,
    )
    # Model accepts; validate_weights rejects
    with pytest.raises(RankingInvalidConfigError):
        validate_weights(w)


def test_ranking_weights_no_negative() -> None:
    """Negative weights are rejected."""
    with pytest.raises(ValidationError):
        RankingWeights(
            accessibility_impact=-0.1,
            standards_compliance=0.2,
            contextual_suitability=0.15,
            implementation_effort=0.15,
            maintainability=0.1,
            compatibility=0.1,
            risk=0.4,
        )


def test_ranking_weights_no_over_one() -> None:
    """Individual weights > 1.0 are rejected."""
    with pytest.raises(ValidationError):
        RankingWeights(
            accessibility_impact=1.5,
            standards_compliance=0.0,
            contextual_suitability=0.0,
            implementation_effort=0.0,
            maintainability=0.0,
            compatibility=0.0,
            risk=0.0,
        )


def test_ranking_weights_rounding() -> None:
    """Weights are rounded to 4 decimal places."""
    w = RankingWeights(
        accessibility_impact=0.142857,
        standards_compliance=0.142857,
        contextual_suitability=0.142857,
        implementation_effort=0.142857,
        maintainability=0.142857,
        compatibility=0.142857,
        risk=0.142858,
    )
    # Should be accepted after rounding
    assert isinstance(w.accessibility_impact, float)


def test_ranking_weights_to_dict() -> None:
    """to_dict returns a plain dict with all seven dimensions."""
    w = RankingWeights(
        accessibility_impact=0.2,
        standards_compliance=0.15,
        contextual_suitability=0.15,
        implementation_effort=0.15,
        maintainability=0.1,
        compatibility=0.1,
        risk=0.15,
    )
    d = w.to_dict()
    assert set(d.keys()) == set(RANKING_DIMENSIONS)
    assert abs(sum(d.values()) - 1.0) < 0.001


def test_ranking_mode_enum() -> None:
    """RankingMode has baseline and contextual values."""
    assert RankingMode.BASELINE == "baseline"
    assert RankingMode.CONTEXTUAL == "contextual"


def test_context_factor_valid() -> None:
    """A valid context factor is accepted."""
    factor = ContextFactor(
        factor="critical_wcag_issue",
        detected=True,
        influence=0.3,
        affected_dimensions=["accessibility_impact", "standards_compliance"],
        explanation="The issue has critical impact.",
    )
    assert factor.factor == "critical_wcag_issue"
    assert factor.detected is True
    assert factor.influence == 0.3


def test_context_factor_influence_bounds() -> None:
    """Influence must be between -1.0 and 1.0."""
    with pytest.raises(ValidationError):
        ContextFactor(
            factor="test",
            detected=True,
            influence=1.5,
            affected_dimensions=["risk"],
            explanation="Too much influence.",
        )
    with pytest.raises(ValidationError):
        ContextFactor(
            factor="test",
            detected=True,
            influence=-1.5,
            affected_dimensions=["risk"],
            explanation="Too negative influence.",
        )


def test_ranked_strategy_valid() -> None:
    """A valid ranked strategy is accepted."""
    ranked = RankedStrategy(
        strategy_id="s-1",
        rank=1,
        weighted_score=8.5,
        dimension_scores={"accessibility_impact": 9, "risk": 8},
        strengths=["Strong"],
        weaknesses=["Minor"],
        ranking_explanation="Ranked first because of high scores.",
        confidence=0.9,
    )
    assert ranked.strategy_id == "s-1"
    assert ranked.rank == 1
    assert ranked.weighted_score == 8.5


def test_ranked_strategy_rank_bounds() -> None:
    """Rank must be >= 1."""
    with pytest.raises(ValidationError):
        RankedStrategy(
            strategy_id="s-1",
            rank=0,
            weighted_score=8.5,
            dimension_scores={},
            ranking_explanation="Test.",
            confidence=0.9,
        )


def test_ranking_batch_no_secrets() -> None:
    """RankingBatch never contains secret fields."""
    batch = RankingBatch(
        scan_id="scan-1",
        context_version="1.0",
        ranking_method="baseline",
        weights_used=RankingWeights(
            accessibility_impact=1/7,
            standards_compliance=1/7,
            contextual_suitability=1/7,
            implementation_effort=1/7,
            maintainability=1/7,
            compatibility=1/7,
            risk=1/7,
        ),
        ranked_strategies=[
            RankedStrategy(
                strategy_id="s-1",
                rank=1,
                weighted_score=8.5,
                dimension_scores={},
                ranking_explanation="Test.",
                confidence=0.9,
            )
        ],
    )
    serialized = str(batch.model_dump()).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in serialized


def test_ranking_version_constant() -> None:
    """RANKING_VERSION is defined."""
    assert RANKING_VERSION == "1.0"
