"""Remediation domain exceptions (Module 7).

Mirrors the evaluation/strategy/project exception pattern: every error
carries an HTTP ``status_code`` and a stable, machine-readable ``code``,
rendered as the uniform ``{code, message}`` envelope by the handler
registered in :mod:`app.api.errors`. Messages are always sanitized —
internal details never leak to clients.
"""


class RemediationError(Exception):
    """Base class for all remediation errors."""

    status_code = 500
    code = "remediation_error"


class RemediationNotFoundError(RemediationError):
    """The requested remediation proposal does not exist. → 404."""

    status_code = 404
    code = "remediation_not_found"


class RemediationTargetNotFoundError(RemediationError):
    """The requested issue or strategy does not exist for this scan. → 404."""

    status_code = 404
    code = "remediation_target_not_found"


class RemediationStrategyNotRankedError(RemediationError):
    """The strategy is not the recommended (top-ranked) strategy. → 409."""

    status_code = 409
    code = "strategy_not_recommended"


class RemediationInvalidTransitionError(RemediationError):
    """The requested status transition is not allowed. → 409."""

    status_code = 409
    code = "remediation_invalid_transition"


class RemediationProviderError(RemediationError):
    """The remediation provider failed at runtime. → 502."""

    status_code = 502
    code = "remediation_provider_error"


class RemediationOutputError(RemediationError):
    """The provider returned invalid output. → 502."""

    status_code = 502
    code = "remediation_output_invalid"
