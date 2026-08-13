"""Authentication domain.

Batch 2 wires the real Supabase provider; Batch 2 finalization verifies
access tokens asymmetrically against the project's **JWKS endpoint** (no
shared secret). The provider abstraction, bearer dependency, and protected
``/me`` route are unchanged. Without credentials the app still runs on the
placeholder provider (auth endpoints answer 501).
"""

from app.auth.exceptions import (
    AuthConfigurationError,
    AuthError,
    AuthNotConfiguredError,
    AuthenticationRequiredError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserNotFoundError,
)
from app.auth.interfaces import (
    AuthResult,
    AuthService,
    AuthUser,
    ResetPasswordInput,
    SignInInput,
    SignUpInput,
)
from app.auth.jwt import (
    JWTService,
    TokenDecoder,
    TokenEncoder,
    TokenPair,
    TokenPayload,
)
from app.auth.jwks import SupabaseJwtVerifier
from app.auth.providers import (
    SupabaseAuthProvider,
    get_auth_provider,
)

__all__ = [
    "AuthConfigurationError",
    "AuthError",
    "AuthNotConfiguredError",
    "AuthenticationRequiredError",
    "AuthResult",
    "AuthService",
    "AuthUser",
    "EmailAlreadyRegisteredError",
    "EmailNotVerifiedError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "JWTService",
    "ResetPasswordInput",
    "SignInInput",
    "SignUpInput",
    "SupabaseAuthProvider",
    "SupabaseJwtVerifier",
    "TokenDecoder",
    "TokenEncoder",
    "TokenExpiredError",
    "TokenPair",
    "TokenPayload",
    "UserNotFoundError",
    "get_auth_provider",
]
