"""Authentication domain contracts.

These interfaces are the only thing the API layer and dependency injection may
depend on. Concrete providers (Supabase, Firebase, Auth0, …) implement
:class:`AuthService` and are selected in :mod:`app.auth.providers.registry` —
no route or service code needs to change when the provider is swapped.
"""

from typing import Optional, Protocol

from pydantic import BaseModel


class AuthUser(BaseModel):
    """A resolved user identity, provider-agnostic."""

    id: str
    email: str
    display_name: Optional[str] = None
    email_verified: bool = False


class AuthResult(BaseModel):
    """Outcome of a successful sign-in / sign-up."""

    user: AuthUser
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class SignUpInput(BaseModel):
    """Contract passed to ``sign_up``."""

    email: str
    password: str
    display_name: Optional[str] = None


class SignInInput(BaseModel):
    """Contract passed to ``sign_in``."""

    email: str
    password: str


class ResetPasswordInput(BaseModel):
    """Contract passed to ``reset_password``."""

    token: str
    new_password: str


class AuthService(Protocol):
    """Contract every authentication provider must implement."""

    async def get_current_user(self) -> Optional[AuthUser]:
        """Return the current user, or ``None`` when unauthenticated."""
        ...

    async def verify_access_token(self, token: str) -> AuthUser:
        """Validate a bearer token and return its user.

        :raises InvalidTokenError: malformed token or bad signature.
        :raises TokenExpiredError: the token has expired.
        """
        ...

    async def sign_up(self, payload: SignUpInput) -> AuthResult:
        """Create an account and return the new session."""
        ...

    async def sign_in(self, payload: SignInInput) -> AuthResult:
        """Authenticate credentials and return a session."""
        ...

    async def sign_out(self) -> None:
        """Invalidate the current session."""
        ...

    async def request_password_reset(self, email: str) -> None:
        """Start a password-reset flow for ``email``."""
        ...

    async def reset_password(self, payload: ResetPasswordInput) -> None:
        """Complete a password reset with a token."""
        ...

    async def verify_email(self, token: str) -> None:
        """Verify an email address with a token."""
        ...
