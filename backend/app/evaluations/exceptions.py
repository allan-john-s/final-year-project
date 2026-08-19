"""Evaluation domain exceptions (Module 5).

Mirrors the strategy/auth/project/scan exception pattern: every error carries
an HTTP ``status_code`` and a stable, machine-readable ``code``, rendered as
the uniform ``{code, message}`` envelope by the handler registered in
:mod:`app.api.errors`. Messages are always sanitized — provider internals,
response bodies and credentials never leak to clients.
"""


class EvaluationError(Exception):
    """Base class for all evaluation errors."""

    status_code = 500
    code = "evaluation_error"


class EvaluationConfigurationError(EvaluationError):
    """The evaluator provider is not configured (e.g. missing API key). → 503.

    Raised before any network call; the app never substitutes a fake
    evaluator when the real provider is requested but unconfigured.
    """

    status_code = 503
    code = "evaluation_configuration_error"


class EvaluationTargetNotFoundError(EvaluationError):
    """The requested issue/group does not exist for this scan. → 404.

    One safe 404 covers both "missing" and "not part of this scan's
    context" so responses never leak whether a target exists elsewhere.
    """

    status_code = 404
    code = "evaluation_target_not_found"


class EvaluationStrategyInvalidError(EvaluationError):
    """A supplied strategy does not match the selected scan/target context.

    Strategies are generated on demand (never persisted), so the evaluator
    must not trust client-supplied ids — every strategy is re-validated
    against the deterministic ContextDocument (issue membership, context
    version, evidence reference). Mismatches answer 422 (invalid payload).
    """

    status_code = 422
    code = "evaluation_strategy_invalid"


class EvaluationProviderError(EvaluationError):
    """The evaluator provider failed at runtime (timeout, rate limit,
    network). → 502."""

    status_code = 502
    code = "evaluation_provider_error"


class EvaluationOutputError(EvaluationError):
    """The provider returned output that fails validation. → 502.

    Raw provider responses are never echoed back; only a sanitized message.
    """

    status_code = 502
    code = "evaluation_output_invalid"
