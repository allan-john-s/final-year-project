"""JWT payload models and token protocols.

The protocols define what the rest of the app may depend on. Verification is
performed against Supabase's **JWKS endpoint** in :mod:`app.auth.jwks` — this
module deliberately contains no shared-secret verification and no signing
logic: Supabase issues the tokens, we only verify them with public keys.

``TokenPayload`` is the provider-agnostic claims model consumed by providers,
dependencies, and the middleware.
"""

from datetime import datetime, timezone
from typing import Optional, Protocol

from pydantic import BaseModel, Field

from app.auth.interfaces import AuthUser


class TokenPayload(BaseModel):
    """Claims carried by an access token."""

    sub: str
    exp: datetime
    iat: datetime
    aud: Optional[str] = None
    jti: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    email: Optional[str] = None
    email_verified: bool = False
    display_name: Optional[str] = None


class TokenPair(BaseModel):
    """Access + refresh token pair issued on sign-in."""

    access_token: str
    refresh_token: str


class TokenEncoder(Protocol):
    """Signs a payload into a token string."""

    def encode(
        self,
        payload: TokenPayload,
        *,
        secret: str,
        algorithm: str = "HS256",
    ) -> str:
        ...


class TokenDecoder(Protocol):
    """Verifies a token string and recovers its payload."""

    def decode(
        self,
        token: str,
        *,
        secret: str,
        algorithm: str = "HS256",
    ) -> TokenPayload:
        ...


class JWTService(Protocol):
    """Token lifecycle facade used by auth providers."""

    async def create_token_pair(self, user: AuthUser) -> TokenPair:
        """Issue a fresh access/refresh pair for ``user``."""
        ...

    async def decode_access_token(self, token: str) -> TokenPayload:
        """Validate an access token and return its claims."""
        ...


def _to_utc(timestamp: int) -> datetime:
    """Convert a Unix epoch timestamp to an aware UTC datetime."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
