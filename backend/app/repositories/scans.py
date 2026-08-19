"""Supabase-backed scan repository.

Talks to the Supabase PostgREST API (``/rest/v1/scans``) with the
**service-role key** — the same key the auth provider uses for GoTrue and
the project repository uses. Because the service key bypasses RLS, ownership
is enforced here in the query filters (``user_id=eq.<id>``) on every read and
write; RLS in the database protects direct client access. Defense in depth.

Row → :class:`Scan` mapping keeps the rest of the app storage-agnostic.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import Settings
from app.scans.exceptions import ScanConfigurationError, ScanError
from app.scans.models import Scan, ScanCreate, ScanStatus, ScanUpdate
from app.scanners.models import ScannerType

_TIMEOUT = httpx.Timeout(10.0)
_SCANS_PATH = "/rest/v1/scans"


class SupabaseScanRepository:
    """CRUD for scans against the Supabase PostgREST endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- helpers ----------------------------------------------------------

    @property
    def _base_url(self) -> str:
        return self._settings.supabase_url.rstrip("/")

    def _require_config(self) -> None:
        """Raise a config error before any network call when unconfigured."""
        if not self._settings.supabase_url or not self._settings.supabase_service_role_key:
            raise ScanConfigurationError(
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
        """Map a PostgREST error response onto :class:`ScanError`."""
        if response.is_success:
            return
        raise ScanError(
            f"{operation} failed ({response.status_code}): {self._error_message(response)}"
        )

    @staticmethod
    def _row_to_scan(row: Dict[str, Any]) -> Scan:
        return Scan(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            user_id=str(row["user_id"]),
            scanner_type=ScannerType(row.get("scanner_type") or ScannerType.RESEARCH.value),
            status=ScanStatus(row.get("status") or ScanStatus.PENDING.value),
            started_at=_parse_iso(row["started_at"]) if row.get("started_at") else None,
            completed_at=_parse_iso(row["completed_at"]) if row.get("completed_at") else None,
            duration_ms=row.get("duration_ms"),
            summary=row.get("summary") or {},
            total_issues=int(row.get("total_issues") or 0),
            critical_count=int(row.get("critical_count") or 0),
            serious_count=int(row.get("serious_count") or 0),
            moderate_count=int(row.get("moderate_count") or 0),
            minor_count=int(row.get("minor_count") or 0),
            accessibility_score=row.get("accessibility_score"),
            scanner_name=row.get("scanner_name"),
            scanner_version=row.get("scanner_version"),
            wcag_version=row.get("wcag_version"),
            scan_url=row.get("scan_url"),
            scan_depth=int(row.get("scan_depth") or 1),
            pages_scanned=int(row.get("pages_scanned") or 0),
            browser_name=row.get("browser_name"),
            browser_version=row.get("browser_version"),
            user_agent=row.get("user_agent"),
            total_dom_elements=int(row.get("total_dom_elements") or 0),
            tested_elements=int(row.get("tested_elements") or 0),
            normalization_duration_ms=row.get("normalization_duration_ms"),
            persistence_duration_ms=row.get("persistence_duration_ms"),
            created_at=_parse_iso(row["created_at"]),
        )

    # --- ScanRepository ----------------------------------------------------

    async def create(self, data: ScanCreate) -> Scan:
        self._require_config()
        body: Dict[str, Any] = {
            "project_id": data.project_id,
            "user_id": data.user_id,
            "scanner_type": data.scanner_type.value,
            "status": data.status.value,
        }
        if data.scan_url is not None:
            body["scan_url"] = data.scan_url
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={"select": "*"},
                json=body,
            )
        self._raise_for_status(response, "create scan")
        rows = response.json()
        return self._row_to_scan(rows[0])

    async def get(self, user_id: str, scan_id: str) -> Optional[Scan]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(),
                params={
                    "id": f"eq.{scan_id}",
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                    "limit": "1",
                },
            )
        self._raise_for_status(response, "get scan")
        rows = response.json()
        return self._row_to_scan(rows[0]) if rows else None

    async def list_for_project(self, user_id: str, project_id: str) -> List[Scan]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "project_id": f"eq.{project_id}",
                    "order": "created_at.desc",
                    "select": "*",
                },
            )
        self._raise_for_status(response, "list scans")
        return [self._row_to_scan(row) for row in response.json()]

    async def list_for_user(self, user_id: str) -> List[Scan]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                    "select": "*",
                },
            )
        self._raise_for_status(response, "list scans")
        return [self._row_to_scan(row) for row in response.json()]

    async def update(
        self,
        user_id: str,
        scan_id: str,
        changes: ScanUpdate,
    ) -> Optional[Scan]:
        self._require_config()
        body = changes.model_dump(mode="json", exclude_none=True)
        if not body:
            # Nothing to change — return the current row if it exists.
            return await self.get(user_id, scan_id)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.patch(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={
                    "id": f"eq.{scan_id}",
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                },
                json=body,
            )
        self._raise_for_status(response, "update scan")
        rows = response.json()
        return self._row_to_scan(rows[0]) if rows else None

    async def delete(self, user_id: str, scan_id: str) -> bool:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.delete(
                f"{self._base_url}{_SCANS_PATH}",
                headers=self._headers(Prefer="return=representation"),
                params={
                    "id": f"eq.{scan_id}",
                    "user_id": f"eq.{user_id}",
                },
            )
        self._raise_for_status(response, "delete scan")
        return len(response.json()) > 0


_FRACTIONAL_SECONDS = re.compile(r"\.(\d+)([+-]|$)")


def _parse_iso(value: str) -> datetime:
    """Parse a PostgREST ISO-8601 timestamp (``Z`` or ``+00:00`` suffix).

    PostgREST serializes timestamps via Postgres ``to_json``, which trims
    trailing zeros in the fractional seconds (``.874710`` → ``.87471``) — pad
    the fraction back to 6 digits so ``fromisoformat`` accepts it on Python 3.9.
    """
    normalized = value.replace("Z", "+00:00")

    def _pad(match: "re.Match[str]") -> str:
        fraction = match.group(1)[:6].ljust(6, "0")
        return f".{fraction}{match.group(2)}"

    normalized = _FRACTIONAL_SECONDS.sub(_pad, normalized)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
