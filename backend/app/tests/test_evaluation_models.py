"""Tests for the evaluation domain models (Module 5).

Covers EvaluationDraft/StrategyEvaluation field bounds (all seven scores are
bounded 0–10), the documented effort/risk semantics at the field level, the
evaluation version default, the deliberate absence of total/rank fields, the
evaluation request schema (target requirement + strategy_ids/strategies
consistency), and list sanitization.
"""

import pytest
from pydantic import ValidationError

from app.evaluations.models import (
    EVALUATION_VERSION,
    EvaluationBatch,
    EvaluationDraft,
    StrategyEvaluation,
)
from app.schemas.evaluations import StrategyEvaluateRequest
from app.tests.test_strategy_models import make_strategy


def make_draft(**overrides) -> dict:
    """A valid EvaluationDraft payload dict."""
    data = {
        "strategy_id": "native-label-association",
        "accessibility_impact_score": 9,
        "standards_compliance_score": 9,
        "contextual_suitability_score": 8,
        "implementation_effort_score": 8,
        "maintainability_score": 9,
        "compatibility_score": 9,
        "risk_score": 8,
        "strengths": ["Native semantics are exposed to assistive technology."],
        "weaknesses": ["A native element may change default styling."],
        "rationale": "Native HTML is the most robust fix for this rule.",
        "assumptions": ["The page source is editable."],
        "uncertainties": ["Manual screen-reader verification is still required."],
        "evidence_references": ["issue-1"],
    }
    data.update(overrides)
    return data


def make_evaluation(**overrides) -> dict:
    """A valid full StrategyEvaluation payload dict."""
    data = {
        **make_draft(),
        "evaluation_id": "eval-native-label-association",
        "scan_id": "scan-1",
        "issue_id": "issue-1",
        "group_id": None,
        "context_version": "1.0",
        "evaluator_provider": "mock",
        "evaluator_model": "mock-model",
        "prompt_version": "1.0",
    }
    data.update(overrides)
    return data


def test_valid_draft_roundtrips() -> None:
    draft = EvaluationDraft.model_validate(make_draft())

    assert draft.strategy_id == "native-label-association"
    assert draft.accessibility_impact_score == 9
    assert draft.evidence_references == ["issue-1"]


@pytest.mark.parametrize("field", [
    "accessibility_impact_score",
    "standards_compliance_score",
    "contextual_suitability_score",
    "implementation_effort_score",
    "maintainability_score",
    "compatibility_score",
    "risk_score",
])
def test_every_score_is_bounded_0_to_10(field) -> None:
    assert EvaluationDraft.model_validate(make_draft(**{field: 0})).model_dump()[field] == 0
    assert EvaluationDraft.model_validate(make_draft(**{field: 10})).model_dump()[field] == 10
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(**{field: -1}))
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(**{field: 11}))


def test_all_seven_scores_are_required() -> None:
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(accessibility_impact_score=None))


def test_strategies_require_strengths_and_weaknesses() -> None:
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(strengths=[]))
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(weaknesses=[]))
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(strengths=["   ", "  "]))


def test_effort_and_risk_semantics_are_separate_fields() -> None:
    """Effort (10 = easy) and risk (10 = low risk) are distinct dimensions —
    a model can hold high effort with low risk, and vice versa."""
    easy_low_risk = EvaluationDraft.model_validate(
        make_draft(implementation_effort_score=10, risk_score=10)
    )
    hard_high_risk = EvaluationDraft.model_validate(
        make_draft(implementation_effort_score=0, risk_score=0)
    )
    assert easy_low_risk.implementation_effort_score == 10
    assert easy_low_risk.risk_score == 10
    assert hard_high_risk.implementation_effort_score == 0
    assert hard_high_risk.risk_score == 0


def test_evaluation_version_defaults_to_1_0() -> None:
    evaluation = StrategyEvaluation.model_validate(make_evaluation())
    assert evaluation.evaluation_version == EVALUATION_VERSION == "1.0"


def test_evaluation_has_no_total_score_and_no_rank() -> None:
    """The research separation: Module 5 produces multidimensional evidence
    only — no combined score and no ranking field."""
    fields = StrategyEvaluation.model_fields
    assert "total_score" not in fields
    assert "rank" not in fields
    assert "weighted_score" not in fields


def test_evaluation_never_accepts_secret_fields() -> None:
    evaluation = StrategyEvaluation.model_validate(make_evaluation())
    dumped = str(evaluation.model_dump()).lower()
    for forbidden in ("api_key", "secret", "token", "password", "authorization", "bearer"):
        assert forbidden not in dumped


def test_list_fields_are_sanitized() -> None:
    draft = EvaluationDraft.model_validate(
        make_draft(strengths=["  strong  ", "", "  "], uncertainties=["  unsure  "])
    )
    assert draft.strengths == ["strong"]
    assert draft.uncertainties == ["unsure"]


def test_rationale_length_limits() -> None:
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(make_draft(rationale="x" * 4001))


def test_batch_requires_at_least_one_evaluation() -> None:
    evaluation = StrategyEvaluation.model_validate(make_evaluation())
    batch = EvaluationBatch(
        scan_id="scan-1",
        issue_id="issue-1",
        context_version="1.0",
        evaluation_version="1.0",
        prompt_version="1.0",
        provider="mock",
        model="mock-model",
        evaluations=[evaluation],
    )
    assert len(batch.evaluations) == 1
    with pytest.raises(ValidationError):
        EvaluationBatch(
            scan_id="scan-1",
            context_version="1.0",
            evaluation_version="1.0",
            prompt_version="1.0",
            provider="mock",
            model="mock-model",
            evaluations=[],
        )


# --- request schema ----------------------------------------------------------

def make_request(**overrides) -> dict:
    data = {
        "issue_id": "issue-1",
        "strategy_ids": ["native-1"],
        "strategies": [make_strategy(strategy_id="native-1", issue_id="issue-1")],
    }
    data.update(overrides)
    return data


def test_evaluate_request_requires_a_target() -> None:
    with pytest.raises(ValidationError):
        StrategyEvaluateRequest(
            strategy_ids=["native-1"],
            strategies=[make_strategy(strategy_id="native-1")],
        )
    assert StrategyEvaluateRequest(**make_request()).issue_id == "issue-1"
    assert StrategyEvaluateRequest(
        group_id="rule:x",
        strategy_ids=["native-1"],
        strategies=[make_strategy(strategy_id="native-1")],
    ).group_id == "rule:x"


def test_evaluate_request_strategy_ids_must_match_strategies() -> None:
    with pytest.raises(ValidationError):
        StrategyEvaluateRequest(
            issue_id="issue-1",
            strategy_ids=["other-id"],
            strategies=[make_strategy(strategy_id="native-1")],
        )
    # extra id with no matching strategy
    with pytest.raises(ValidationError):
        StrategyEvaluateRequest(
            issue_id="issue-1",
            strategy_ids=["native-1", "ghost"],
            strategies=[make_strategy(strategy_id="native-1")],
        )


def test_evaluate_request_list_bounds() -> None:
    with pytest.raises(ValidationError):
        StrategyEvaluateRequest(issue_id="issue-1", strategy_ids=[], strategies=[])
    with pytest.raises(ValidationError):
        StrategyEvaluateRequest(
            issue_id="issue-1",
            strategy_ids=[f"s{i}" for i in range(11)],
            strategies=[make_strategy(strategy_id=f"s{i}") for i in range(11)],
        )
