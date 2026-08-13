"""Application settings, loaded from environment variables and ``.env``.

Settings are cached with ``functools.lru_cache`` so every consumer receives
the same frozen configuration object.
"""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Accessibility Remediation API"
    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # --- Supabase (authentication provider) ---
    # Read from SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. Empty by default so
    # the app runs and tests pass without credentials; the provider registry
    # falls back to the not-implemented provider then. Access tokens are
    # verified asymmetrically via the project's JWKS endpoint — no JWT secret.
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Comma-separated list of allowed CORS origins (e.g. "http://a,http://b").
    # ``NoDecode`` disables pydantic-settings' JSON decoding for complex types
    # so the comma-separated form reaches the validator below as a raw string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accept either a JSON array or a comma-separated env string."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def strip_trailing_slashes(cls, value: list[str]) -> list[str]:
        return [origin.rstrip("/") for origin in value]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
