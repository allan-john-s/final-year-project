"""Supabase authentication provider.

Implements :class:`AuthService` against Supabase Auth (GoTrue):

- **Token verification** is asymmetric: access tokens are RS256 JWTs verified
  against the project's JWKS endpoint (see
  :class:`app.auth.jwks.SupabaseJwtVerifier`). No shared secret is needed and
  no token is ever issued by this backend.
- **Account / session operations** go through the GoTrue REST API using the
  **service role key** — user passwords never travel through this backend and
  are never stored here.

Provider methods raise the shared :class:`AuthError` hierarchy, so routes and
the exception handler need no knowledge of Supabase.
"""

from typing import Any, Dict, Optional

import httpx

from app.auth.exceptions import (
    AuthConfigurationError,
    AuthError,
    AuthenticationRequiredError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from app.auth.interfaces import (
    AuthResult,
    AuthUser,
    ResetPasswordInput,
    SignInInput,
    SignUpInput,
)
from app.auth.jwks import SupabaseJwtVerifier, get_supabase_verifier
from app.auth.providers.base import AuthProvider
from app.core.config import Settings

_TIMEOUT = httpx.Timeout(10.0)


class SupabaseAuthProvider(AuthProvider):
    """Concrete provider backed by Supabase Auth."""

    name = "supabase"

    def __init__(
        self,
        settings: Settings,
        *,
        verifier: Optional[SupabaseJwtVerifier] = None,
    ) -> None:
        self._settings = settings
        self._verifier = verifier

    # --- helpers ----------------------------------------------------------

    def _require(self, value: str, env_name: str, operation: str) -> None:
        if not value:
            raise AuthConfigurationError(
                f"Supabase {env_name} is not configured; cannot {operation}. "
                "Add it to backend/.env (see .env.example)."
            )

    @property
    def _base_url(self) -> str:
        return self._settings.supabase_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self._settings.supabase_service_role_key,
            "Authorization": f"Bearer {self._settings.supabase_service_role_key}",
        }

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        """Map a GoTrue error response onto the auth exception hierarchy."""
        if response.is_success:
            return
        message = _error_message(response)
        if response.status_code in (400, 409, 422) and "registered" in message.lower():
            raise EmailAlreadyRegisteredError(message)
        if response.status_code == 404:
            raise UserNotFoundError(message)
        if response.status_code in (400, 401, 403):
            raise InvalidCredentialsError(message)
        raise AuthError(f"{operation} failed ({response.status_code}): {message}")

    # --- AuthService ------------------------------------------------------

    async def verify_access_token(self, token: str) -> AuthUser:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "verify access tokens")
        verifier = self._verifier or get_supabase_verifier(self._settings.supabase_url)
        payload = await verifier.verify(token)
        return AuthUser(
            id=payload.sub,
            email=payload.email or payload.sub,
            display_name=payload.display_name,
            email_verified=payload.email_verified,
        )

    async def get_current_user(self) -> Optional[AuthUser]:
        # No token context is available here — protected routes use the bearer
        # dependency (app.dependencies.auth.get_current_user) instead.
        raise AuthenticationRequiredError("A bearer token is required.")

    async def sign_up(self, payload: SignUpInput) -> AuthResult:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "create accounts")
        self._require(
            self._settings.supabase_service_role_key,
            "SUPABASE_SERVICE_ROLE_KEY",
            "create accounts",
        )
        body: Dict[str, Any] = {"email": payload.email, "password": payload.password}
        if payload.display_name:
            body["user_metadata"] = {"display_name": payload.display_name}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/auth/v1/admin/users",
                headers=self._headers(),
                json=body,
            )
        self._raise_for_status(response, "sign up")
        return AuthResult(user=_user_from_gotrue(response.json()))

    async def sign_in(self, payload: SignInInput) -> AuthResult:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "sign users in")
        self._require(
            self._settings.supabase_service_role_key,
            "SUPABASE_SERVICE_ROLE_KEY",
            "sign users in",
        )

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/auth/v1/token?grant_type=password",
                headers=self._headers(),
                json={"email": payload.email, "password": payload.password},
            )
        self._raise_for_status(response, "sign in")

        data = response.json()
        return AuthResult(
            user=_user_from_gotrue(data.get("user") or {}),
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
        )

    async def sign_out(self) -> None:
        # JWTs are stateless; the client revokes its own refresh token via
        # supabase-js `signOut()`. Nothing to invalidate server-side without
        # the user's access token.
        return None

    async def request_password_reset(self, email: str) -> None:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "send reset emails")
        self._require(
            self._settings.supabase_service_role_key,
            "SUPABASE_SERVICE_ROLE_KEY",
            "send reset emails",
        )

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}/auth/v1/recover",
                headers=self._headers(),
                json={"email": email},
            )
        self._raise_for_status(response, "request password reset")

    async def reset_password(self, payload: ResetPasswordInput) -> None:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "reset passwords")
        # The recovery token from the reset email doubles as a short-lived
        # bearer credential for the user.
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.put(
                f"{self._base_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {payload.token}"},
                json={"password": payload.new_password},
            )
        self._raise_for_status(response, "reset password")

    async def verify_email(self, token: str) -> None:
        self._require(self._settings.supabase_url, "SUPABASE_URL", "verify emails")
        self._require(
            self._settings.supabase_service_role_key,
            "SUPABASE_SERVICE_ROLE_KEY",
            "verify emails",
        )

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # The token in the confirmation link is a hash, not a 6-digit OTP:
            # GoTrue's /verify expects it as ``token_hash`` (the same mapping
            # supabase-js applies in verifyOtp).
            response = await client.post(
                f"{self._base_url}/auth/v1/verify",
                headers=self._headers(),
                json={"type": "signup", "token_hash": token},
            )
        self._raise_for_status(response, "verify email")


def _user_from_gotrue(data: Dict[str, Any]) -> AuthUser:
    """Map a GoTrue user object onto the provider-agnostic :class:`AuthUser`."""
    metadata = data.get("user_metadata") or {}
    display_name = metadata.get("display_name") if isinstance(metadata, dict) else None
    return AuthUser(
        id=str(data.get("id", "")),
        email=str(data.get("email") or ""),
        display_name=display_name,
        email_verified=bool(data.get("email_confirmed_at")),
    )


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or "Supabase request failed."
    if isinstance(body, dict):
        for key in ("msg", "message", "error_description", "error"):
            if body.get(key):
                return str(body[key])
        return "Supabase request failed."
    return str(body) or "Supabase request failed."
