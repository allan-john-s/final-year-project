"""Scan domain exceptions.

Mirrors the project/auth exception pattern: every error carries an HTTP
``status_code`` and a stable, machine-readable ``code``. The handler
registered in :mod:`app.api.errors` renders them as the uniform
``{code, message}`` envelope.
"""


class ScanError(Exception):
    """Base class for all scan errors."""

    status_code = 500
    code = "scan_error"


class ScanNotFoundError(ScanError):
    """The scan does not exist or is not owned by the caller. → 404.

    A single 404 is used for both "missing" and "not yours" so responses
    never leak whether another user's scan exists (IDOR-safe).
    """

    status_code = 404
    code = "scan_not_found"


class ScanConfigurationError(ScanError):
    """Supabase is selected but a required credential is missing. → 503."""

    status_code = 503
    code = "scan_configuration_error"


class InvalidScanTransitionError(ScanError):
    """A scan cannot move from its current status to the requested one. → 409.

    Lifecycle is strictly ``PENDING → RUNNING → COMPLETED/FAILED``; a
    client-visible transition (e.g. completing a PENDING scan) is rejected.
    """

    status_code = 409
    code = "invalid_scan_transition"


class ScanExecutionError(ScanError):
    """The scanner run failed; the row has been marked FAILED. → 500.

    The message is the sanitized failure text stored on the scan row
    (``summary.error``) — never a raw stack trace.
    """

    status_code = 500
    code = "scan_execution_failed"
