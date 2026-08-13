"""Tests for application settings parsing."""

from app.core.config import Settings


def test_cors_origins_defaults() -> None:
    settings = Settings()
    assert settings.cors_origins == ["http://localhost:5173"]


def test_cors_origins_parses_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://example.com/")
    settings = Settings()
    assert settings.cors_origins == ["http://localhost:5173", "http://example.com"]


def test_cors_origins_parses_json_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test", "http://b.test"]')
    settings = Settings()
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
