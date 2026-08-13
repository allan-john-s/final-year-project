"""Root endpoint: ``GET /`` service metadata."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.service import ServiceInfo

router = APIRouter()


@router.get("/", response_model=ServiceInfo, tags=["meta"])
def get_service_info() -> ServiceInfo:
    """Return identifying metadata for the API service."""
    settings = get_settings()
    return ServiceInfo(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        docs="/docs",
    )
