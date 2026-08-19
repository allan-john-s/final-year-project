"""Context domain exceptions.

Mirrors the auth/project/scan exception pattern: every error carries an HTTP
``status_code`` and a stable, machine-readable ``code``, rendered as the
uniform ``{code, message}`` envelope by the handler registered in
:mod:`app.api.errors`.
"""


class ContextError(Exception):
    """Base class for all context errors."""

    status_code = 500
    code = "context_error"


class ContextUnavailableError(ContextError):
    """The scan exists but context cannot be built yet (not COMPLETED). → 409.

    Context is only meaningful once a scan has finished; PENDING/RUNNING
    scans answer 409 so clients can poll and retry when ready.
    """

    status_code = 409
    code = "context_unavailable"
