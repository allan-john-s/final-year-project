"""Aggregate router for the whole HTTP surface.

Infrastructure endpoints (``/``, ``/health``) live at the root; versioned
business endpoints (``/api/v1``) are mounted below them.
"""

from fastapi import APIRouter

from app.api.routes import auth, health, projects, root

api_router = APIRouter()
api_router.include_router(root.router)
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/api/v1")
api_router.include_router(projects.router, prefix="/api/v1")
