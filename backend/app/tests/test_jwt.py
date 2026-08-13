"""Unit tests for JWKS-based access token verification (RS256).

Tokens are minted locally with a throwaway RSA key and verified through
:class:`app.auth.jwks.SupabaseJwtVerifier` whose JWKS endpoint is served
in-memory — no network, no real credentials.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.auth.exceptions import (
    AuthConfigurationError,
    InvalidTokenError,
    TokenExpiredError,
)
from app.auth.jwks import SupabaseJwtVerifier, get_supabase_verifier
from app.tests.conftest import (
    AUDIENCE,
    BASE_URL,
    base_claims,
    jwks_document,
    make_failing_verifier,
    make_verifier,
    mint_token,
)


def verify(verifier: SupabaseJwtVerifier, token: str) -> Any:
    """Run the async verifier synchronously."""
    return asyncio.run(verifier.verify(token))


def test_verify_returns_claims_for_a_valid_token(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    payload = verify(verifier, mint_token(rsa_private_key, base_claims()))

    assert payload.sub == "user-1"
    assert payload.email == "user-1@example.com"
    assert payload.email_verified is True
    assert payload.display_name == "Ada"
    assert payload.aud == AUDIENCE


def test_verify_accepts_es256_keys(rsa_private_key) -> None:
    """The new Supabase signing system serves ES256 JWKS keys — verify the
    algorithm is picked up from the JWK rather than hardcoded."""
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec

    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()
    nums = public.public_numbers()
    coord_len = (public.curve.key_size + 7) // 8

    def _b64u(n: int, length: int) -> str:
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    jwks = {
        "keys": [
            {
                "kty": "EC",
                "kid": "es256-kid",
                "use": "sig",
                "alg": "ES256",
                "crv": "P-256",
                "x": _b64u(nums.x, coord_len),
                "y": _b64u(nums.y, coord_len),
            }
        ]
    }
    client = PyJWKClient(f"{BASE_URL}/auth/v1/.well-known/jwks.json")
    client.fetch_data = lambda: jwks  # type: ignore[method-assign]
    verifier = SupabaseJwtVerifier(BASE_URL, client=client)

    token = pyjwt.encode(base_claims(), private, algorithm="ES256", headers={"kid": "es256-kid"})
    payload = verify(verifier, token)
    assert payload.sub == "user-1"


def test_verify_rejects_token_signed_by_a_different_key(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    other_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
    token = mint_token(other_key, base_claims())

    with pytest.raises(InvalidTokenError):
        verify(verifier, token)


def test_verify_rejects_expired_token(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    claims = base_claims(exp=datetime.now(timezone.utc) - timedelta(minutes=5))

    with pytest.raises(TokenExpiredError):
        verify(verifier, mint_token(rsa_private_key, claims))


def test_verify_rejects_wrong_issuer(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    claims = base_claims(iss="https://evil.example/auth/v1")

    with pytest.raises(InvalidTokenError):
        verify(verifier, mint_token(rsa_private_key, claims))


def test_verify_rejects_wrong_audience(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    claims = base_claims(aud="mobile")

    with pytest.raises(InvalidTokenError):
        verify(verifier, mint_token(rsa_private_key, claims))


def test_verify_rejects_missing_required_claims(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    claims = base_claims()
    del claims["exp"]

    with pytest.raises(InvalidTokenError):
        verify(verifier, mint_token(rsa_private_key, claims))


def test_verify_rejects_malformed_token(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))

    with pytest.raises(InvalidTokenError):
        verify(verifier, "not-a-jwt")


def test_verify_rejects_tampered_payload(rsa_private_key) -> None:
    verifier = make_verifier(jwks_document(rsa_private_key))
    token = mint_token(rsa_private_key, base_claims())
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload[:-1] + ('A' if payload[-1] != 'A' else 'B')}.{signature}"

    with pytest.raises(InvalidTokenError):
        verify(verifier, tampered)


def test_verify_refetches_jwks_on_unknown_kid(rsa_private_key) -> None:
    """Key rotation: an unknown ``kid`` triggers a fresh JWKS fetch."""
    rotated_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)

    # First fetch serves only the old key; the second serves the rotated key.
    documents = [
        jwks_document(rsa_private_key, kid="old-key"),
        jwks_document(rotated_key, kid="new-key"),
    ]
    client = PyJWKClient(f"{BASE_URL}/auth/v1/.well-known/jwks.json")
    client.fetch_data = lambda: documents.pop(0)  # type: ignore[method-assign]
    verifier = SupabaseJwtVerifier(BASE_URL, client=client)

    token = mint_token(rotated_key, base_claims(), kid="new-key")
    payload = verify(verifier, token)
    assert payload.sub == "user-1"


def test_verify_raises_configuration_error_when_jwks_unreachable(
    rsa_private_key,
) -> None:
    verifier = make_failing_verifier(PyJWKClientConnectionError("boom"))

    with pytest.raises(AuthConfigurationError):
        verify(verifier, mint_token(rsa_private_key, base_claims()))


def test_verifier_derives_issuer_and_jwks_url() -> None:
    verifier = SupabaseJwtVerifier("https://proj.supabase.co")
    assert verifier.issuer == "https://proj.supabase.co/auth/v1"
    assert (
        verifier.jwks_url
        == "https://proj.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_get_supabase_verifier_is_cached_per_url() -> None:
    get_supabase_verifier.cache_clear()
    try:
        first = get_supabase_verifier("https://proj.supabase.co")
        second = get_supabase_verifier("https://proj.supabase.co")
        other = get_supabase_verifier("https://other.supabase.co")
        assert first is second
        assert first is not other
    finally:
        get_supabase_verifier.cache_clear()
