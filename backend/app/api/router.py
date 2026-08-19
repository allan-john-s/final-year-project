"""Aggregate router for the whole HTTP surface.

Infrastructure endpoints (``/``, ``/health``) live at the root; versioned
business endpoints (``/api/v1``) are mounted below them.
"""

from fastapi import APIRouter

from app.api.routes import auth, context, evaluations, health, projects, rankings, remediations, root, scans, strategies

api_router = APIRouter()
api_router.include_router(root.router)
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/api/v1")
api_router.include_router(projects.router, prefix="/api/v1")
api_router.include_router(scans.router, prefix="/api/v1")
api_router.include_router(scans.project_router, prefix="/api/v1")
api_router.include_router(context.router, prefix="/api/v1")
api_router.include_router(strategies.router, prefix="/api/v1")
api_router.include_router(evaluations.router, prefix="/api/v1")
api_router.include_router(rankings.router, prefix="/api/v1")
api_router.include_router(remediations.router, prefix="/api/v1")
api_router.include_router(remediations.remediation_router, prefix="/api/v1")
