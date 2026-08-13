"""Project domain exceptions.

Mirrors the auth exception pattern: every error carries an HTTP ``status_code``
and a stable, machine-readable ``code``. The handler registered in
:mod:`app.api.errors` renders them as the uniform ``{code, message}`` envelope.
"""


class ProjectError(Exception):
    """Base class for all project errors."""

    status_code = 500
    code = "project_error"


class ProjectNotFoundError(ProjectError):
    """The project does not exist or is not owned by the caller. → 404.

    A single 404 is used for both "missing" and "not yours" so responses never
    leak whether another user's project exists (IDOR-safe).
    """

    status_code = 404
    code = "project_not_found"


class ProjectConfigurationError(ProjectError):
    """Supabase is selected but a required credential is missing. → 503."""

    status_code = 503
    code = "project_configuration_error"
