"""Health endpoint: ``GET /health`` liveness probe."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.service import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health_check() -> HealthResponse:
    """Return a liveness payload used by orchestrators and uptime monitors."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.app_env,
    )
