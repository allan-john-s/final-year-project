"""Strategy ranking domain exceptions (Module 6).

Mirrors the evaluation/strategy/project exception pattern: every error
carries an HTTP ``status_code`` and a stable, machine-readable ``code``,
rendered as the uniform ``{code, message}`` envelope by the handler
registered in :mod:`app.api.errors`. Messages are always sanitized —
internal details never leak to clients.
"""


class RankingError(Exception):
    """Base class for all ranking errors."""

    status_code = 500
    code = "ranking_error"


class RankingTargetNotFoundError(RankingError):
    """The requested issue/group does not exist for this scan. → 404.

    One safe 404 covers both "missing" and "not part of this scan's
    context" so responses never leak whether a target exists elsewhere.
    """

    status_code = 404
    code = "ranking_target_not_found"


class RankingEvaluationsNotFoundError(RankingError):
    """No evaluations are available for the selected strategies. → 409.

    The caller must generate and evaluate strategies before ranking.
    """

    status_code = 409
    code = "ranking_evaluations_not_found"


class RankingInvalidConfigError(RankingError):
    """The supplied ranking configuration is invalid. → 422."""

    status_code = 422
    code = "ranking_config_invalid"
