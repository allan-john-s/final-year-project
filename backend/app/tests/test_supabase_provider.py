"""Tests for the Supabase auth provider.

The GoTrue REST calls are replaced with a fake transport so the provider is
exercised without network access or real credentials. Access-token
verification runs through the JWKS verifier with an in-memory JWKS document.
"""

import asyncio

import httpx
import pytest

from app.auth.exceptions import (
    AuthConfigurationError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.auth.interfaces import AuthUser, ResetPasswordInput, SignInInput, SignUpInput
from app.auth.providers.supabase import SupabaseAuthProvider
from app.core.config import Settings
from app.tests.conftest import base_claims, jwks_document, make_verifier, mint_token

USER_JSON = {
    "id": "user-1",
    "email": "dev@example.com",
    "email_confirmed_at": "2026-01-01T00:00:00Z",
    "user_metadata": {"display_name": "Ada"},
}


def _settings(**overrides) -> Settings:
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-role-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _provider(rsa_private_key, **settings_overrides) -> SupabaseAuthProvider:
    """Provider with an in-memory JWKS-backed verifier."""
    verifier = make_verifier(jwks_document(rsa_private_key))
    return SupabaseAuthProvider(_settings(**settings_overrides), verifier=verifier)


def _jwt(rsa_private_key, sub: str = "user-1") -> str:
    return mint_token(rsa_private_key, base_claims(sub=sub, email=f"{sub}@example.com"))


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict) -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._json


class FakeAsyncClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    async def put(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("put", url, kwargs))
        return self.responses.pop(0)


def _patch_http(monkeypatch, *responses) -> FakeAsyncClient:
    client = FakeAsyncClient(responses)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    return client


def test_provider_requires_credentials_before_network_calls(
    monkeypatch, rsa_private_key
) -> None:
    provider = SupabaseAuthProvider(_settings(supabase_url="", supabase_service_role_key=""))

    with pytest.raises(AuthConfigurationError):
        asyncio.run(provider.sign_up(SignUpInput(email="dev@example.com", password="secret1")))

    with pytest.raises(AuthConfigurationError):
        asyncio.run(provider.verify_access_token(_jwt(rsa_private_key)))


def test_verify_access_token_maps_claims_to_user(rsa_private_key) -> None:
    provider = _provider(rsa_private_key)
    user = asyncio.run(provider.verify_access_token(_jwt(rsa_private_key)))

    assert user == AuthUser(
        id="user-1",
        email="user-1@example.com",
        display_name="Ada",
        email_verified=True,
    )


def test_verify_access_token_rejects_invalid_token(rsa_private_key) -> None:
    provider = _provider(rsa_private_key)
    with pytest.raises(InvalidTokenError):
        asyncio.run(provider.verify_access_token("garbage"))


def test_verify_access_token_rejects_token_with_wrong_issuer(rsa_private_key) -> None:
    provider = _provider(rsa_private_key)
    token = mint_token(rsa_private_key, base_claims(iss="https://evil.example/auth/v1"))
    with pytest.raises(InvalidTokenError):
        asyncio.run(provider.verify_access_token(token))


def test_verify_access_token_rejects_expired_token(rsa_private_key) -> None:
    from datetime import datetime, timedelta, timezone

    from app.auth.exceptions import TokenExpiredError

    provider = _provider(rsa_private_key)
    token = mint_token(
        rsa_private_key,
        base_claims(exp=datetime.now(timezone.utc) - timedelta(minutes=5)),
    )
    with pytest.raises(TokenExpiredError):
        asyncio.run(provider.verify_access_token(token))


def test_sign_up_creates_user_via_admin_api(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    client = _patch_http(
        monkeypatch,
        FakeResponse(201, {**USER_JSON, "email_confirmed_at": None}),
    )

    result = asyncio.run(
        provider.sign_up(
            SignUpInput(email="dev@example.com", password="secret1", display_name="Ada")
        )
    )

    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/auth/v1/admin/users"
    assert kwargs["json"] == {
        "email": "dev@example.com",
        "password": "secret1",
        "user_metadata": {"display_name": "Ada"},
    }
    assert "service-role-key" in kwargs["headers"]["Authorization"]
    assert result.user.email == "dev@example.com"
    assert result.user.email_verified is False


def test_sign_up_maps_already_registered_error(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    _patch_http(
        monkeypatch,
        FakeResponse(422, {"msg": "A user with this email address has already been registered"}),
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        asyncio.run(provider.sign_up(SignUpInput(email="dev@example.com", password="secret1")))


def test_sign_in_returns_tokens_and_user(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    client = _patch_http(
        monkeypatch,
        FakeResponse(
            200,
            {
                "access_token": "access-123",
                "refresh_token": "refresh-123",
                "user": USER_JSON,
            },
        ),
    )

    result = asyncio.run(provider.sign_in(SignInInput(email="dev@example.com", password="secret1")))

    assert client.calls[0][1] == "https://example.supabase.co/auth/v1/token?grant_type=password"
    assert result.access_token == "access-123"
    assert result.refresh_token == "refresh-123"
    assert result.user.display_name == "Ada"


def test_sign_in_maps_invalid_credentials(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    _patch_http(
        monkeypatch,
        FakeResponse(
            400,
            {"error": "invalid_grant", "error_description": "Invalid login credentials"},
        ),
    )

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(provider.sign_in(SignInInput(email="dev@example.com", password="wrong")))


def test_request_password_reset_posts_to_recover(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    client = _patch_http(monkeypatch, FakeResponse(200, {}))

    asyncio.run(provider.request_password_reset("dev@example.com"))

    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/auth/v1/recover"
    assert kwargs["json"] == {"email": "dev@example.com"}


def test_reset_password_uses_recovery_token_as_bearer(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    client = _patch_http(monkeypatch, FakeResponse(200, {}))

    asyncio.run(
        provider.reset_password(ResetPasswordInput(token="recovery-tok", new_password="newsecret1"))
    )

    method, url, kwargs = client.calls[0]
    assert method == "put"
    assert url == "https://example.supabase.co/auth/v1/user"
    assert kwargs["headers"]["Authorization"] == "Bearer recovery-tok"
    assert kwargs["json"] == {"password": "newsecret1"}


def test_verify_email_posts_to_verify(monkeypatch) -> None:
    provider = SupabaseAuthProvider(_settings())
    client = _patch_http(monkeypatch, FakeResponse(200, {}))

    asyncio.run(provider.verify_email("verify-tok"))

    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/auth/v1/verify"
    assert kwargs["json"] == {"type": "signup", "token": "verify-tok"}


def test_sign_out_is_stateless() -> None:
    provider = SupabaseAuthProvider(_settings())
    assert asyncio.run(provider.sign_out()) is None
