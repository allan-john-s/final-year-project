"""Evaluation domain (Module 5).

Evaluates every candidate remediation strategy independently across seven
bounded dimensions. Deliberately no ranking / winner selection — that is
Module 6's responsibility.
"""

from app.evaluations.models import (
    EVALUATION_VERSION,
    EVALUATION_CRITERIA,
    EvaluationBatch,
    EvaluationDraft,
    StrategyEvaluation,
    StrategyEvaluationRequest,
)
from app.evaluations.services import StrategyEvaluationService

__all__ = [
    "EVALUATION_VERSION",
    "EVALUATION_CRITERIA",
    "EvaluationBatch",
    "EvaluationDraft",
    "StrategyEvaluation",
    "StrategyEvaluationRequest",
    "StrategyEvaluationService",
]
