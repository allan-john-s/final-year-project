"""Tests for the strategy domain models (Module 4).

Covers CandidateStrategy field bounds, controlled enums, confidence range,
WCAG alignment normalization, list sanitization, the generation
metadata/traceability models, and the API request validation (target
requirement + strategy count bounds).
"""

import pytest
from pydantic import ValidationError

from app.strategies.models import (
    CandidateStrategy,
    EffortRating,
    ImpactRating,
    StrategyGeneration,
    StrategyGenerationMetadata,
    StrategyType,
)
from app.schemas.strategies import StrategyGenerateRequest


def make_strategy(**overrides) -> dict:
    """A valid CandidateStrategy payload dict."""
    data = {
        "strategy_id": "native-label-association",
        "strategy_index": 1,
        "issue_id": "issue-1",
        "group_id": None,
        "context_version": "1.0",
        "strategy_type": "native_html",
        "title": "Associate the input with a native label element",
        "summary": "Wrap the control in a native <label>.",
        "rationale": "Native labels are exposed to the accessibility tree.",
        "implementation_steps": ["Add a <label> element.", "Verify with axe."],
        "expected_accessibility_impact": "high",
        "wcag_alignment": ["4.1.2", "1.3.1"],
        "implementation_effort": "low",
        "maintainability_notes": "Low maintenance.",
        "compatibility_notes": "Broad support.",
        "risks": ["Possible styling changes."],
        "assumptions": ["The page source is editable."],
        "confidence": 0.85,
        "evidence_reference": "issue-1",
    }
    data.update(overrides)
    return data


def test_valid_strategy_roundtrips() -> None:
    strategy = CandidateStrategy.model_validate(make_strategy())

    assert strategy.strategy_type is StrategyType.NATIVE_HTML
    assert strategy.implementation_effort is EffortRating.LOW
    assert strategy.expected_accessibility_impact is ImpactRating.HIGH
    assert strategy.confidence == 0.85
    assert strategy.wcag_alignment == ["1.3.1", "4.1.2"]  # sorted


def test_title_required_and_bounded() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(title=""))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(title="x" * 201))
    # whitespace-only title fails min_length after stripping
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(title="   "))


def test_confidence_range_enforced() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(confidence=1.5))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(confidence=-0.1))
    assert CandidateStrategy.model_validate(make_strategy(confidence=1.0)).confidence == 1.0


def test_invalid_enums_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(strategy_type="not-a-type"))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(implementation_effort="huge"))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(expected_accessibility_impact="critical"))


def test_strategy_index_bounds() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(strategy_index=0))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(strategy_index=6))


def test_implementation_steps_required_and_sanitized() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(implementation_steps=[]))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(
            make_strategy(implementation_steps=["  ", "  "])
        )

    strategy = CandidateStrategy.model_validate(
        make_strategy(implementation_steps=["  step one  ", "step two", ""])
    )
    assert strategy.implementation_steps == ["step one", "step two"]


def test_wcag_alignment_is_sorted_and_deduplicated() -> None:
    strategy = CandidateStrategy.model_validate(
        make_strategy(wcag_alignment=["4.1.2", "1.3.1", "4.1.2"])
    )
    assert strategy.wcag_alignment == ["1.3.1", "4.1.2"]


def test_string_field_length_limits() -> None:
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(summary="x" * 2001))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(rationale="x" * 4001))
    with pytest.raises(ValidationError):
        CandidateStrategy.model_validate(make_strategy(strategy_id="x" * 65))


def test_generation_metadata_never_accepts_secret_fields() -> None:
    metadata = StrategyGenerationMetadata(
        scan_id="scan-1",
        target_type="issue",
        issue_id="issue-1",
        context_version="1.0",
        prompt_version="1.0",
        provider="mock",
        model="mock-model",
        temperature=0.2,
        strategy_count=3,
    )
    assert metadata.generated_at is not None
    assert "api_key" not in metadata.model_dump()
    assert "token" not in metadata.model_dump()


def test_strategy_generation_requires_2_to_5_strategies() -> None:
    metadata = StrategyGenerationMetadata(
        scan_id="scan-1", target_type="issue", issue_id="issue-1",
        context_version="1.0", prompt_version="1.0", provider="mock",
        model="m", temperature=0.2, strategy_count=3,
    )
    one = [CandidateStrategy.model_validate(make_strategy(strategy_id="a", strategy_index=1))]
    with pytest.raises(ValidationError):
        StrategyGeneration(metadata=metadata, strategies=one)

    six = [
        CandidateStrategy.model_validate(
            make_strategy(strategy_id=f"s{i}", strategy_index=(i % 5) + 1)
        )
        for i in range(1, 7)
    ]
    with pytest.raises(ValidationError):
        StrategyGeneration(metadata=metadata, strategies=six)

    two = [
        CandidateStrategy.model_validate(make_strategy(strategy_id="a", strategy_index=1)),
        CandidateStrategy.model_validate(make_strategy(strategy_id="b", strategy_index=2)),
    ]
    assert len(StrategyGeneration(metadata=metadata, strategies=two).strategies) == 2


# --- request schema ----------------------------------------------------------


def test_generate_request_requires_a_target() -> None:
    with pytest.raises(ValidationError):
        StrategyGenerateRequest()
    assert StrategyGenerateRequest(issue_id="issue-1").issue_id == "issue-1"
    assert StrategyGenerateRequest(group_id="rule:x").group_id == "rule:x"
    assert (
        StrategyGenerateRequest(issue_id="i", group_id="g").issue_id == "i"
    )


def test_generate_request_count_bounds() -> None:
    assert StrategyGenerateRequest(issue_id="i").strategy_count == 3
    assert StrategyGenerateRequest(issue_id="i", strategy_count=5).strategy_count == 5
    with pytest.raises(ValidationError):
        StrategyGenerateRequest(issue_id="i", strategy_count=1)
    with pytest.raises(ValidationError):
        StrategyGenerateRequest(issue_id="i", strategy_count=6)
