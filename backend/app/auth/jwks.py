"""JWKS-based verification of Supabase access tokens.

Supabase signs access tokens asymmetrically (RS256) with keys that rotate over
time. This module verifies them against the project's JWKS endpoint using
PyJWT's :class:`jwt.PyJWKClient` — a maintained JWT/JWK library — which
handles fetching, caching (with a TTL), matching a token's ``kid`` to a signing
key, and transparently refetching when a ``kid`` is unknown (key rotation).

The legacy ``SUPABASE_JWT_SECRET`` / HS256 shared-secret path is intentionally
gone: verification here needs only the project URL and the *public* signing
keys. The verifier enforces, at minimum:

- **signature** — never trust claims before the signature is verified,
- **issuer (``iss``)** — must equal ``https://<project-ref>.supabase.co/auth/v1``,
- **audience (``aud``)** — must be ``authenticated``,
- **expiration (``exp``)** and **subject (``sub``)** — present and valid.

Failures map onto the shared auth exception hierarchy so the error envelope
and the middleware/dependency plumbing stay unchanged.
"""

import asyncio
from functools import lru_cache
import ssl
from typing import Any, Dict, Optional

import certifi
import jwt as _jwt
from jwt import PyJWKClient

from app.auth.exceptions import (
    AuthConfigurationError,
    InvalidTokenError,
    TokenExpiredError,
)
from app.auth.jwt import TokenPayload, _to_utc

AUDIENCE = "authenticated"
JWKS_PATH = "/auth/v1/.well-known/jwks.json"
ISSUER_PATH = "/auth/v1"
JWKS_LIFESPAN_SECONDS = 300.0
JWKS_TIMEOUT_SECONDS = 10.0


class SupabaseJwtVerifier:
    """Verify a Supabase access token against a project's JWKS endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        audience: str = AUDIENCE,
        lifespan: float = JWKS_LIFESPAN_SECONDS,
        timeout: float = JWKS_TIMEOUT_SECONDS,
        client: Optional[PyJWKClient] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        base_url = base_url.rstrip("/")
        self._issuer = f"{base_url}{ISSUER_PATH}"
        self._jwks_url = f"{base_url}{JWKS_PATH}"
        self._audience = audience
        if client is None:
            if ssl_context is None:
                ssl_context = ssl.create_default_context(cafile=certifi.where())
            client = PyJWKClient(
                self._jwks_url,
                lifespan=lifespan,
                timeout=timeout,
                ssl_context=ssl_context,
            )
        self._client = client

    @property
    def issuer(self) -> str:
        """The expected ``iss`` claim for this project."""
        return self._issuer

    @property
    def jwks_url(self) -> str:
        """The JWKS endpoint used to resolve signing keys."""
        return self._jwks_url

    async def verify(self, token: str) -> TokenPayload:

        """Validate ``token`` and return its verified claims.

        The signature is checked first; only then are ``iss`` / ``aud`` /
        ``exp`` / ``sub`` enforced, so unverified claims are never trusted.

        :raises TokenExpiredError: the token is past its ``exp``.
        :raises InvalidTokenError: bad signature, wrong issuer/audience,
            missing required claims, malformed token, or unknown signing key.
        :raises AuthConfigurationError: the JWKS endpoint is unreachable.
        """
        try:
            signing_key = await asyncio.to_thread(
                self._client.get_signing_key_from_jwt, token
            )
        except _jwt.PyJWKClientConnectionError as exc:
            raise AuthConfigurationError(
                "Could not reach the Supabase JWKS endpoint to verify tokens."
            ) from exc
        except _jwt.PyJWTError as exc:
            raise InvalidTokenError("The access token is invalid.") from exc

        try:
            claims = _jwt.decode(
                token,
                signing_key.key,
                algorithms=[_algorithm_for(signing_key)],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["sub", "exp", "iat", "iss", "aud"],
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except _jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("The access token has expired.") from exc
        except _jwt.PyJWTError as exc:
            raise InvalidTokenError("The access token is invalid.") from exc

        return _claims_to_payload(claims)


def _algorithm_for(signing_key) -> str:
    """Resolve the verification algorithm from the matched JWK.

    Prefer the JWK's explicit ``alg`` (e.g. ES256 for the new Supabase signing
    keys); fall back to the key type so we never guess RS256 for an EC key.
    """
    if signing_key.algorithm_name:
        return signing_key.algorithm_name
    key_type = signing_key.key_type or ""
    if key_type == "EC":
        return "ES256"
    if key_type == "RSA":
        return "RS256"
    return "RS256"


def _claims_to_payload(claims: Dict[str, Any]) -> TokenPayload:

    """Map verified JWT claims onto the shared :class:`TokenPayload` model."""
    user_metadata = claims.get("user_metadata")
    display_name = None
    if isinstance(user_metadata, dict):
        display_name = user_metadata.get("display_name")
    return TokenPayload(
        sub=str(claims["sub"]),
        exp=_to_utc(claims["exp"]),
        iat=_to_utc(claims["iat"]),
        aud=claims.get("aud"),
        jti=claims.get("jti"),
        scopes=list(claims.get("scopes") or []),
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified", False)),
        display_name=display_name,
    )


@lru_cache(maxsize=8)
def get_supabase_verifier(base_url: str) -> SupabaseJwtVerifier:
    """Return a cached :class:`SupabaseJwtVerifier` for ``base_url``.

    The verifier (and its :class:`PyJWKClient`) is shared across requests so
    the JWKS document is fetched once and cached until the TTL expires or the
    ``kid`` rotates. Key rotation is handled by the client automatically: an
    unknown ``kid`` triggers a fresh fetch.
    """
    return SupabaseJwtVerifier(base_url)
