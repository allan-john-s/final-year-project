"""Response schemas for the foundation endpoints."""

from typing import Literal

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    """Metadata returned by ``GET /``."""

    service: str
    version: str
    environment: str
    docs: str


class HealthResponse(BaseModel):
    """Liveness payload returned by ``GET /health``."""

    status: Literal["ok"]
    version: str
    environment: str
