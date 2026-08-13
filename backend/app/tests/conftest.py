"""Shared pytest fixtures.

- ``isolated_settings`` (autouse): neutralizes any real credentials in
  ``backend/.env`` so the suite always runs against the placeholder provider
  unless a test explicitly constructs a Supabase provider.
- RS256/JWKS helpers: mint asymmetric access tokens and build verifiers whose
  JWKS document is served in-memory (no network, no real keys).
"""

import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

from app.auth.jwks import SupabaseJwtVerifier
from app.core.config import get_settings

AUDIENCE = "authenticated"
BASE_URL = "https://example.supabase.co"
ISSUER = f"{BASE_URL}/auth/v1"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Force empty Supabase credentials so tests never touch the real project."""
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def rsa_private_key():
    """A fresh RSA-2048 private key for a single test."""
    return rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def jwks_document(private_key: Any, kid: str = "test-key-1") -> Dict[str, Any]:
    """Build a JWKS document containing ``private_key``'s public key."""
    public = private_key.public_key()
    numbers = public.public_numbers()
    modulus_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(modulus_bytes),
                "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }


def mint_token(private_key: Any, claims: Dict[str, Any], kid: str = "test-key-1") -> str:
    """Sign ``claims`` as an RS256 JWT with the given ``kid``."""
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def base_claims(**overrides: Any) -> Dict[str, Any]:
    """Supabase-like claims for a valid access token (aud/iss as expected)."""
    now = datetime.now(timezone.utc)
    claims: Dict[str, Any] = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "email": "user-1@example.com",
        "email_verified": True,
        "user_metadata": {"display_name": "Ada"},
    }
    claims.update(overrides)
    return claims


def make_verifier(
    jwks: Dict[str, Any],
    *,
    base_url: str = BASE_URL,
    lifespan: float = 300.0,
) -> SupabaseJwtVerifier:
    """Build a verifier that serves ``jwks`` in-memory (no HTTP)."""
    from jwt import PyJWKClient

    client = PyJWKClient(f"{base_url}/auth/v1/.well-known/jwks.json")
    client.fetch_data = lambda: jwks  # type: ignore[method-assign]
    return SupabaseJwtVerifier(base_url, client=client, lifespan=lifespan)


def failing_fetcher(exc: Exception) -> Callable[[], Dict[str, Any]]:
    """A JWKS fetcher that always raises (simulates an unreachable endpoint)."""

    def _fetch() -> Dict[str, Any]:
        raise exc

    return _fetch


def make_failing_verifier(exc: Exception, base_url: str = BASE_URL) -> SupabaseJwtVerifier:
    """Build a verifier whose JWKS fetch always raises."""
    from jwt import PyJWKClient

    client = PyJWKClient(f"{base_url}/auth/v1/.well-known/jwks.json")
    client.fetch_data = failing_fetcher(exc)  # type: ignore[method-assign]
    return SupabaseJwtVerifier(base_url, client=client)
