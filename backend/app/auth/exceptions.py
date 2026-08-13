"""Authentication exception hierarchy.

Every auth error carries an HTTP ``status_code`` and a stable, machine-readable
``code``. Subclasses of :class:`AuthError` are translated to JSON responses by
the handler registered in :mod:`app.api.errors`.
"""


class AuthError(Exception):
    """Base class for all authentication errors."""

    status_code = 500
    code = "auth_error"


class AuthNotConfiguredError(AuthError):
    """Raised until a real provider (e.g. Supabase) is wired up. → 501."""

    status_code = 501
    code = "auth_not_configured"


class AuthConfigurationError(AuthError):
    """A provider is selected but a required credential is missing. → 503."""

    status_code = 503
    code = "auth_configuration_error"


class AuthenticationRequiredError(AuthError):
    """The endpoint requires an authenticated user. → 401."""

    status_code = 401
    code = "authentication_required"


class InvalidCredentialsError(AuthError):
    """Email/password combination did not match. → 401."""

    status_code = 401
    code = "invalid_credentials"


class InvalidTokenError(AuthError):
    """Token was malformed or failed signature validation. → 401."""

    status_code = 401
    code = "invalid_token"


class TokenExpiredError(AuthError):
    """Token has expired. → 401."""

    status_code = 401
    code = "token_expired"


class EmailAlreadyRegisteredError(AuthError):
    """Email is already in use. → 409."""

    status_code = 409
    code = "email_already_registered"


class UserNotFoundError(AuthError):
    """No account matches the identifier. → 404."""

    status_code = 404
    code = "user_not_found"


class EmailNotVerifiedError(AuthError):
    """Account exists but the email is unverified. → 403."""

    status_code = 403
    code = "email_not_verified"
