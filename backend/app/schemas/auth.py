"""Request/response schemas for the auth API surface.

HTTP-layer models: they validate incoming bodies (the frontend runs the same
rules client-side) and shape documented responses. Domain contracts live in
:mod:`app.auth.interfaces`; routes translate between the two.
"""

from typing import Optional

from pydantic import BaseModel, Field

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"


class SignUpRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=8)
    display_name: Optional[str] = Field(default=None, max_length=100)


class SignInRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    """Body for ``POST /auth/password/forgot``."""

    email: str = Field(pattern=_EMAIL_PATTERN)


class ResetPasswordRequest(BaseModel):
    """Body for ``POST /auth/password/reset``."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class VerifyEmailRequest(BaseModel):
    """Body for ``POST /auth/email/verify``."""

    token: str = Field(min_length=1)


class AuthUserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    email_verified: bool = False


class AuthResultResponse(BaseModel):
    user: AuthUserResponse
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class ErrorResponse(BaseModel):
    """Uniform error payload produced by the exception handlers."""

    code: str
    message: str
