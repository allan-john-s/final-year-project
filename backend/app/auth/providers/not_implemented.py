"""Placeholder provider returned until a real one is configured."""

from typing import Optional

from app.auth.exceptions import AuthNotConfiguredError
from app.auth.interfaces import (
    AuthResult,
    AuthUser,
    ResetPasswordInput,
    SignInInput,
    SignUpInput,
)
from app.auth.providers.base import AuthProvider

_MESSAGE = (
    "The authentication provider is not connected yet. Auth endpoints return "
    "501 until a provider (e.g. Supabase) is wired up in a later batch."
)


class NotImplementedAuthProvider(AuthProvider):
    """Every operation raises :class:`AuthNotConfiguredError` (HTTP 501)."""

    name = "not-implemented"

    async def get_current_user(self) -> Optional[AuthUser]:
        raise AuthNotConfiguredError(_MESSAGE)

    async def verify_access_token(self, token: str) -> AuthUser:
        raise AuthNotConfiguredError(_MESSAGE)

    async def sign_up(self, payload: SignUpInput) -> AuthResult:
        raise AuthNotConfiguredError(_MESSAGE)

    async def sign_in(self, payload: SignInInput) -> AuthResult:
        raise AuthNotConfiguredError(_MESSAGE)

    async def sign_out(self) -> None:
        raise AuthNotConfiguredError(_MESSAGE)

    async def request_password_reset(self, email: str) -> None:
        raise AuthNotConfiguredError(_MESSAGE)

    async def reset_password(self, payload: ResetPasswordInput) -> None:
        raise AuthNotConfiguredError(_MESSAGE)

    async def verify_email(self, token: str) -> None:
        raise AuthNotConfiguredError(_MESSAGE)
