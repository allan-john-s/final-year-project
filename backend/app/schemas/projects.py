"""Request/response schemas for the projects API surface.

HTTP-layer models: they validate incoming bodies (the frontend mirrors the
rules client-side) and shape documented responses. Domain contracts live in
:mod:`app.projects.models`; routes translate between the two.

Website URLs are normalized consistently: trimmed, scheme/host lowercased,
default ports dropped, root trailing slash stripped, fragments removed.
Obviously invalid URLs are rejected with 422.
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, model_validator

from app.projects.models import ProjectStatus

_NAME_MIN = 1
_NAME_MAX = 100
_DESCRIPTION_MAX = 2000
_URL_MAX = 2048


def normalize_website_url(value: str) -> str:
    """Validate and normalize a website URL, raising ``ValueError`` when bad."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("website_url must not be empty.")
    if any(char.isspace() for char in stripped):
        raise ValueError("website_url must not contain whitespace.")
    if len(stripped) > _URL_MAX:
        raise ValueError(f"website_url must be at most {_URL_MAX} characters.")

    parts = urlsplit(stripped)
    if parts.scheme not in ("http", "https"):
        raise ValueError("website_url must start with http:// or https://.")
    if not parts.hostname:
        raise ValueError("website_url must include a host.")

    host = parts.hostname.lower()
    netloc = host
    if parts.port is not None:
        default_port = 80 if parts.scheme == "http" else 443
        if parts.port != default_port:
            netloc = f"{host}:{parts.port}"

    path = parts.path
    if path in ("", "/"):
        path = ""

    return urlunsplit((parts.scheme, netloc, path, parts.query, ""))


class ProjectCreateRequest(BaseModel):
    """Body for ``POST /api/v1/projects``. ``user_id`` is intentionally absent
    — ownership always comes from the authenticated request."""

    name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str = Field(default="", max_length=_DESCRIPTION_MAX)
    website_url: str = Field(max_length=_URL_MAX)

    @model_validator(mode="after")
    def _normalize_fields(self) -> "ProjectCreateRequest":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name must not be empty.")
        self.website_url = normalize_website_url(self.website_url)
        return self


class ProjectUpdateRequest(BaseModel):
    """Body for ``PATCH /api/v1/projects/{id}`` — all fields optional, at
    least one required."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=_NAME_MAX)
    description: Optional[str] = Field(default=None, max_length=_DESCRIPTION_MAX)
    website_url: Optional[str] = Field(default=None, max_length=_URL_MAX)
    status: Optional[ProjectStatus] = None

    @model_validator(mode="after")
    def _validate_patch(self) -> "ProjectUpdateRequest":
        if not any(
            value is not None
            for value in (self.name, self.description, self.website_url, self.status)
        ):
            raise ValueError("At least one field must be provided.")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("name must not be empty.")
        if self.website_url is not None:
            self.website_url = normalize_website_url(self.website_url)
        return self


class ProjectResponse(BaseModel):
    """A project as returned by the API (never includes ``user_id``)."""

    id: str
    name: str
    description: str
    website_url: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
