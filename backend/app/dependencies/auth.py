"""Auth dependencies for route handlers.

- :func:`get_auth_service` — the provider DI seam.
- :func:`get_current_user` — resolves the authenticated user from a Bearer
  token; raises a 401 :class:`AuthError` when missing or invalid. It reuses
  the user cached by :class:`app.api.middleware.AuthenticationMiddleware`
  (which verifies the token once per request) when available.
"""

from typing import Annotated, Optional

from fastapi import Depends, Request

from app.auth.exceptions import AuthenticationRequiredError
from app.auth.interfaces import AuthService, AuthUser
from app.auth.providers.registry import get_auth_provider


def get_auth_service() -> AuthService:
    """Resolve the configured authentication provider (DI seam)."""
    return get_auth_provider()


def _bearer_token(request: Request) -> Optional[str]:
    """Extract the Bearer token from the Authorization header, or raise 401."""
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationRequiredError("A bearer token is required.")
    return token.strip()


async def get_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthUser:
    """Resolve the authenticated user from the request's bearer token."""
    cached = getattr(request.state, "auth_user", None)
    if cached is not None:
        return cached
    token = _bearer_token(request)
    return await service.verify_access_token(token)
