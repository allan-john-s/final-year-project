"""Application entry point.

Exposes ``app`` (the ASGI application) plus ``create_app()`` for test
isolation — tests build a fresh app per run.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import AuthenticationMiddleware
from app.api.router import api_router
from app.auth.providers.registry import get_auth_provider
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure a FastAPI application instance."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(
        AuthenticationMiddleware,
        get_service=get_auth_provider,
    )

    register_exception_handlers(application)

    application.include_router(api_router)

    return application


app = create_app()
