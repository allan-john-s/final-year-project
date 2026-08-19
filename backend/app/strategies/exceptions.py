"""Strategy domain exceptions.

Mirrors the auth/project/scan/context exception pattern: every error carries
an HTTP ``status_code`` and a stable, machine-readable ``code``, rendered as
the uniform ``{code, message}`` envelope by the handler registered in
:mod:`app.api.errors`. Messages are always sanitized — provider internals,
response bodies and credentials never leak to clients.
"""


class StrategyError(Exception):
    """Base class for all strategy errors."""

    status_code = 500
    code = "strategy_error"


class StrategyConfigurationError(StrategyError):
    """The LLM provider is not configured (e.g. missing API key). → 503.

    Raised before any network call; the app never substitutes a fake
    generator when the real provider is requested but unconfigured.
    """

    status_code = 503
    code = "strategy_configuration_error"


class StrategyTargetNotFoundError(StrategyError):
    """The requested issue/group does not exist for this scan. → 404.

    One safe 404 covers both "missing" and "not part of this scan's
    context" so responses never leak whether a target exists elsewhere.
    """

    status_code = 404
    code = "strategy_target_not_found"


class StrategyProviderError(StrategyError):
    """The LLM provider failed at runtime (timeout, rate limit, network). → 502."""

    status_code = 502
    code = "strategy_provider_error"


class StrategyOutputError(StrategyError):
    """The provider returned output that fails validation. → 502.

    Raw provider responses are never echoed back; only a sanitized message.
    """

    status_code = 502
    code = "strategy_output_invalid"
