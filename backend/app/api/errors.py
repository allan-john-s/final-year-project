"""Exception → HTTP response mapping for the whole API.

All domain exceptions carry ``status_code`` + ``code`` attributes and render
as the uniform ``{code, message}`` JSON envelope.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth.exceptions import AuthError
from app.context.exceptions import ContextError
from app.evaluations.exceptions import EvaluationError
from app.projects.exceptions import ProjectError
from app.rankings.exceptions import RankingError
from app.remediations.exceptions import RemediationError
from app.scans.exceptions import ScanError
from app.schemas.auth import ErrorResponse
from app.strategies.exceptions import StrategyError


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


def _scan_error_handler(request: Request, exc: ScanError) -> JSONResponse:
    """Render any :class:`ScanError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _context_error_handler(request: Request, exc: ContextError) -> JSONResponse:
    """Render any :class:`ContextError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _strategy_error_handler(request: Request, exc: StrategyError) -> JSONResponse:
    """Render any :class:`StrategyError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _evaluation_error_handler(request: Request, exc: EvaluationError) -> JSONResponse:
    """Render any :class:`EvaluationError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _ranking_error_handler(request: Request, exc: RankingError) -> JSONResponse:
    """Render any :class:`RankingError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def _remediation_error_handler(request: Request, exc: RemediationError) -> JSONResponse:
    """Render any :class:`RemediationError` as a uniform JSON error payload."""
    return _error_response(exc, exc.status_code, exc.code)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all application-level exception handlers to ``app``."""
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.add_exception_handler(ProjectError, _project_error_handler)
    app.add_exception_handler(ScanError, _scan_error_handler)
    app.add_exception_handler(ContextError, _context_error_handler)
    app.add_exception_handler(StrategyError, _strategy_error_handler)
    app.add_exception_handler(EvaluationError, _evaluation_error_handler)
    app.add_exception_handler(RankingError, _ranking_error_handler)
    app.add_exception_handler(RemediationError, _remediation_error_handler)
