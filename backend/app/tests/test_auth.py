"""Tests for the auth infrastructure.

Covers the 501 endpoint surface (placeholder provider), request validation,
the exception → HTTP mapping, the provider registry, the /me endpoint with
JWKS-backed verification, and the interface models.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.api.middleware import AuthenticationMiddleware
from app.auth.exceptions import (
    AuthConfigurationError,
    AuthError,
    AuthNotConfiguredError,
    InvalidCredentialsError,
)
from app.auth.interfaces import (
    AuthResult,
    AuthUser,
    ResetPasswordInput,
    SignInInput,
    SignUpInput,
)
from app.auth.jwt import TokenPayload
from app.auth.providers import (
    NotImplementedAuthProvider,
    get_auth_provider,
)
from app.auth.providers.supabase import SupabaseAuthProvider as ConcreteSupabaseProvider
from app.dependencies.auth import get_auth_service
from app.main import create_app
from app.tests.conftest import base_claims, jwks_document, make_verifier, mint_token


def _auth_client(provider) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: provider
    return TestClient(app)


def _client() -> TestClient:
    return TestClient(create_app())


def test_auth_endpoints_return_501_until_provider_is_connected() -> None:
    client = _client()
    cases = [
        ("post", "/api/v1/auth/signup", {"email": "dev@example.com", "password": "supersecret1", "display_name": "Ada"}),
        ("post", "/api/v1/auth/login", {"email": "dev@example.com", "password": "supersecret1"}),
        ("post", "/api/v1/auth/logout", None),
        ("post", "/api/v1/auth/password/forgot", {"email": "dev@example.com"}),
        ("post", "/api/v1/auth/password/reset", {"token": "tok", "new_password": "supersecret1"}),
        ("post", "/api/v1/auth/email/verify", {"token": "tok"}),
    ]

    for method, path, body in cases:
        if body is None:
            response = getattr(client, method)(path)
        else:
            response = getattr(client, method)(path, json=body)
        assert response.status_code == 501, f"{method.upper()} {path} expected 501"
        payload = response.json()
        assert payload["code"] == "auth_not_configured"
        assert payload["message"]

    # /me is always protected by the bearer dependency: 401 without a token,
    # 501 when the provider is still the placeholder.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["code"] == "authentication_required"

    me_with_token = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer anything"}
    )
    assert me_with_token.status_code == 501
    assert me_with_token.json()["code"] == "auth_not_configured"


def test_auth_endpoints_validate_request_bodies() -> None:
    client = _client()

    bad_email = client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "secret1"},
    )
    assert bad_email.status_code == 422

    short_password = client.post(
        "/api/v1/auth/signup",
        json={"email": "dev@example.com", "password": "short"},
    )
    assert short_password.status_code == 422

    missing_field = client.post(
        "/api/v1/auth/login",
        json={"email": "dev@example.com"},
    )
    assert missing_field.status_code == 422


def test_not_implemented_provider_raises_auth_not_configured() -> None:
    provider = get_auth_provider()
    assert isinstance(provider, NotImplementedAuthProvider)

    with pytest.raises(AuthNotConfiguredError):
        asyncio.run(provider.sign_in(SignInInput(email="dev@example.com", password="secret1")))

    with pytest.raises(AuthNotConfiguredError):
        asyncio.run(provider.get_current_user())


def test_registry_selects_supabase_when_configured(monkeypatch) -> None:
    """SUPABASE_URL set → SupabaseAuthProvider; empty → placeholder.

    An empty env value (not a deletion) is used because pydantic-settings
    prefers the .env file over a missing env var — tests must not depend on
    the developer's local backend/.env.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    get_settings.cache_clear()
    try:
        provider = get_auth_provider()
        assert isinstance(provider, ConcreteSupabaseProvider)
    finally:
        monkeypatch.setenv("SUPABASE_URL", "")
        get_settings.cache_clear()

    provider = get_auth_provider()
    assert isinstance(provider, NotImplementedAuthProvider)


def test_exception_handler_maps_auth_errors_to_json() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise InvalidCredentialsError("Bad credentials")

    response = TestClient(app).get("/boom")

    assert response.status_code == 401
    assert response.json() == {"code": "invalid_credentials", "message": "Bad credentials"}


def test_exception_hierarchy_exposes_http_metadata() -> None:
    assert issubclass(AuthNotConfiguredError, AuthError)
    assert AuthNotConfiguredError.status_code == 501
    assert AuthNotConfiguredError.code == "auth_not_configured"
    assert InvalidCredentialsError.status_code == 401


def test_provider_can_be_swapped_via_dependency_injection() -> None:
    """The DI seam is the only thing that must change for a new provider."""

    class FakeProvider:
        """A minimal stand-in for a real provider (e.g. Supabase)."""

        name = "fake"

        async def get_current_user(self) -> Optional[AuthUser]:
            return AuthUser(id="user-1", email="dev@example.com", email_verified=True)

        async def verify_access_token(self, token: str) -> AuthUser:
            return AuthUser(id="user-1", email="dev@example.com", email_verified=True)

        async def sign_up(self, payload: SignUpInput) -> AuthResult:
            return AuthResult(user=AuthUser(id="user-1", email=payload.email))

        async def sign_in(self, payload: SignInInput) -> AuthResult:
            return AuthResult(
                user=AuthUser(id="user-1", email=payload.email),
                access_token="access",
                refresh_token="refresh",
            )

        async def sign_out(self) -> None:
            return None

        async def request_password_reset(self, email: str) -> None:
            return None

        async def reset_password(self, payload: ResetPasswordInput) -> None:
            return None

        async def verify_email(self, token: str) -> None:
            return None

    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: FakeProvider()
    client = TestClient(app)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "dev@example.com", "password": "supersecret1"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "dev@example.com"
    assert login.json()["access_token"] == "access"

    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer access"})
    assert me.status_code == 200
    assert me.json()["id"] == "user-1"

    me_unauth = client.get("/api/v1/auth/me")
    assert me_unauth.status_code == 401
    assert me_unauth.json()["code"] == "authentication_required"

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204


def test_interface_models_validate() -> None:
    user = AuthUser(id="user-1", email="dev@example.com")
    assert user.display_name is None
    assert user.email_verified is False

    now = datetime.now(timezone.utc)
    payload = TokenPayload(sub="user-1", exp=now, iat=now)
    assert payload.scopes == []
    assert payload.aud is None
    assert payload.email is None


# --- /me with JWKS-backed verification ------------------------------------


class _JwksTokenProvider:
    """A provider whose verify_access_token runs the real JWKS path in-memory."""

    name = "jwks-test"

    def __init__(self, verifier) -> None:
        self._verifier = verifier

    async def verify_access_token(self, token: str) -> AuthUser:
        payload = await self._verifier.verify(token)
        return AuthUser(
            id=payload.sub,
            email=payload.email or payload.sub,
            display_name=payload.display_name,
            email_verified=payload.email_verified,
        )

    async def get_current_user(self) -> Optional[AuthUser]:
        return None

    async def sign_up(self, payload: SignUpInput) -> AuthResult:
        raise AuthNotConfiguredError("unused")

    async def sign_in(self, payload: SignInInput) -> AuthResult:
        raise AuthNotConfiguredError("unused")

    async def sign_out(self) -> None:
        return None

    async def request_password_reset(self, email: str) -> None:
        return None

    async def reset_password(self, payload: ResetPasswordInput) -> None:
        return None

    async def verify_email(self, token: str) -> None:
        return None


def _jwks_token_provider(rsa_private_key):
    verifier = make_verifier(jwks_document(rsa_private_key))
    return _JwksTokenProvider(verifier)


def _me_token(rsa_private_key, sub: str = "user-1", **claim_overrides) -> str:
    claims = base_claims(sub=sub, email=f"{sub}@example.com", **claim_overrides)
    return mint_token(rsa_private_key, claims)


def test_me_returns_user_for_valid_bearer_token(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {_me_token(rsa_private_key)}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "user-1"
    assert body["email"] == "user-1@example.com"
    assert body["email_verified"] is True
    assert body["display_name"] == "Ada"


def test_me_requires_bearer_token(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_me_rejects_invalid_jwt(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_me_rejects_jwt_signed_with_wrong_key(rsa_private_key) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

    client = _auth_client(_jwks_token_provider(rsa_private_key))
    other_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
    token = _me_token(other_key)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_me_rejects_expired_jwt(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    token = _me_token(rsa_private_key, exp=datetime.now(timezone.utc) - timedelta(minutes=5))
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "token_expired"


def test_me_rejects_jwt_with_wrong_issuer(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    token = _me_token(rsa_private_key, iss="https://evil.example/auth/v1")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_me_rejects_jwt_with_wrong_audience(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    token = _me_token(rsa_private_key, aud="mobile")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_me_rejects_non_bearer_scheme(rsa_private_key) -> None:
    client = _auth_client(_jwks_token_provider(rsa_private_key))
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc123"})

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_me_reports_configuration_error_when_jwks_unreachable(rsa_private_key) -> None:
    from jwt.exceptions import PyJWKClientConnectionError

    from app.tests.conftest import make_failing_verifier

    verifier = make_failing_verifier(PyJWKClientConnectionError("boom"))
    provider = _JwksTokenProvider(verifier)

    client = _auth_client(provider)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {_me_token(rsa_private_key)}"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "auth_configuration_error"


def test_authentication_middleware_caches_verified_user(rsa_private_key) -> None:
    app = FastAPI()
    app.add_middleware(
        AuthenticationMiddleware,
        get_service=lambda: _jwks_token_provider(rsa_private_key),
    )

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        user = getattr(request.state, "auth_user", None)
        return {"id": user.id if user else None}

    client = TestClient(app)

    ok = client.get("/whoami", headers={"Authorization": f"Bearer {_me_token(rsa_private_key)}"})
    assert ok.status_code == 200
    assert ok.json()["id"] == "user-1"

    invalid = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
    assert invalid.status_code == 200
    assert invalid.json()["id"] is None

    missing = client.get("/whoami")
    assert missing.status_code == 200
    assert missing.json()["id"] is None
