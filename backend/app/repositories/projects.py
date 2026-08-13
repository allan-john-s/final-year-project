"""Supabase-backed project repository.

Talks to the Supabase PostgREST API (``/rest/v1/projects``) with the
**service-role key** — the same key the auth provider uses for GoTrue. Because
the service key bypasses RLS, ownership is enforced here in the query filters
(``user_id=eq.<id>``) on every read/write; RLS in the database protects direct
client access, this layer protects service-role access. Defense in depth.

Row → :class:`Project` mapping keeps the rest of the app storage-agnostic.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import Settings
from app.projects.exceptions import ProjectConfigurationError, ProjectError
from app.projects.models import Project, ProjectCreate, ProjectStatus, ProjectUpdate

_TIMEOUT = httpx.Timeout(10.0)
_PROJECTS_PATH = "/rest/v1/projects"


class SupabaseProjectRepository:
    """CRUD for projects against the Supabase PostgREST endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- helpers ----------------------------------------------------------

    @property
    def _base_url(self) -> str:
        return self._settings.supabase_url.rstrip("/")

    def _require_config(self) -> None:
        """Raise a config error before any network call when unconfigured."""
        if not self._settings.supabase_url or not self._settings.supabase_service_role_key:
            raise ProjectConfigurationError(
                "Supabase is not configured. Add SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY to backend/.env (see .env.example)."
            )

    def _headers(self, **extra: str) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "apikey": self._settings.supabase_service_role_key,
            "Authorization": f"Bearer {self._settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        headers.update(extra)
        return headers

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        """Extract a safe (non-secret) message from a PostgREST error body."""
        try:
            body = response.json()
        except ValueError:
            return response.text or "Supabase request failed."
        if isinstance(body, dict):
            for key in ("message", "msg", "error", "error_description"):
                if body.get(key):
                    return str(body[key])
        return "Supabase request failed."

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        """Map a PostgREST error response onto :class:`ProjectError`."""
        if response.is_success:
            return
        raise ProjectError(
            f"{operation} failed ({response.status_code}): {self._error_message(response)}"
        )

    @staticmethod
    def _row_to_project(row: Dict[str, Any]) -> Project:
        return Project(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            name=str(row["name"]),
            description=str(row.get("description") or ""),
            website_url=str(row["website_url"]),
            status=ProjectStatus(row.get("status") or ProjectStatus.NOT_SCANNED.value),
            created_at=_parse_iso(row["created_at"]),
            updated_at=_parse_iso(row["updated_at"]),
        )

    # --- ProjectRepository -------------------------------------------------

    async def create(self, data: ProjectCreate) -> Project:
        self._require_config()
        body: Dict[str, Any] = {
            "user_id": data.user_id,
            "name": data.name,
            "description": data.description,
            "website_url": data.website_url,
            "status": data.status.value,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}{_PROJECTS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={"select": "*"},
                json=body,
            )
        self._raise_for_status(response, "create project")
        rows = response.json()
        return self._row_to_project(rows[0])

    async def list_by_user(self, user_id: str) -> List[Project]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_PROJECTS_PATH}",
                headers=self._headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                    "select": "*",
                },
            )
        self._raise_for_status(response, "list projects")
        return [self._row_to_project(row) for row in response.json()]

    async def get(self, user_id: str, project_id: str) -> Optional[Project]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_PROJECTS_PATH}",
                headers=self._headers(),
                params={
                    "id": f"eq.{project_id}",
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                    "limit": "1",
                },
            )
        self._raise_for_status(response, "get project")
        rows = response.json()
        return self._row_to_project(rows[0]) if rows else None

    async def update(
        self,
        user_id: str,
        project_id: str,
        changes: ProjectUpdate,
    ) -> Optional[Project]:
        self._require_config()
        body = changes.model_dump(mode="json", exclude_none=True)
        if not body:
            # Nothing to change — return the current row if it exists.
            return await self.get(user_id, project_id)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.patch(
                f"{self._base_url}{_PROJECTS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={
                    "id": f"eq.{project_id}",
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                },
                json=body,
            )
        self._raise_for_status(response, "update project")
        rows = response.json()
        return self._row_to_project(rows[0]) if rows else None

    async def delete(self, user_id: str, project_id: str) -> bool:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.delete(
                f"{self._base_url}{_PROJECTS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={
                    "id": f"eq.{project_id}",
                    "user_id": f"eq.{user_id}",
                },
            )
        self._raise_for_status(response, "delete project")
        return len(response.json()) > 0


def _parse_iso(value: str) -> datetime:
    """Parse a PostgREST ISO-8601 timestamp (``Z`` or ``+00:00`` suffix)."""
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
