"""ASGI middleware for authentication.

Deliberately non-blocking: it opportunistically decodes a valid Bearer token
and caches the user on ``request.state.auth_user`` so route dependencies
verify at most once per request. Enforcement stays in
:func:`app.dependencies.auth.get_current_user`, which owns the 401 envelope —
the middleware never rejects a request itself.
"""

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.exceptions import AuthError
from app.auth.interfaces import AuthService


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Attach ``request.state.auth_user`` when a valid Bearer token is sent."""

    def __init__(self, app, get_service: Callable[[], AuthService]) -> None:
        super().__init__(app)
        self._service = get_service()

    async def dispatch(self, request: Request, call_next):
        request.state.auth_user = None

        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                request.state.auth_user = await self._service.verify_access_token(token.strip())
            except AuthError:
                # Dependencies produce the authoritative 401 response.
                pass

        return await call_next(request)
