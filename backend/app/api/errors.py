"""Exception → HTTP response mapping for the whole API.

All domain exceptions carry ``status_code`` + ``code`` attributes and render
as the uniform ``{code, message}`` JSON envelope.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth.exceptions import AuthError
from app.projects.exceptions import ProjectError
from app.schemas.auth import ErrorResponse


def _error_response(exc: Exception, status_code: int, code: str) -> JSONResponse:
    """Render any domain exception as the uniform error payload."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=str(exc)).model_dump(),
    )


def _auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    """Render any :class:`AuthError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _project_error_handler(request: Request, exc: ProjectError) -> JSONResponse:
    """Render any :class:`ProjectError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all application-level exception handlers to ``app``."""
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.add_exception_handler(ProjectError, _project_error_handler)
