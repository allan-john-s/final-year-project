"""Supabase-backed accessibility issue repository.

Talks to the Supabase PostgREST API (``/rest/v1/accessibility_issues``) with
the **service-role key**, exactly like the scan/project repositories. Issues
are owned *through their scan*: every read filters with an inner join on the
owning scan's ``user_id``, and writes always carry the ``scan_id`` the
service already verified belongs to the caller. RLS in the database protects
direct client access; this layer protects service-role access. Defense in
depth.

Row → :class:`StoredAccessibilityIssue` mapping keeps the rest of the app
storage-agnostic.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from app.core.config import Settings
from app.scans.exceptions import ScanConfigurationError, ScanError
from app.scans.models import StoredAccessibilityIssue
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel

_TIMEOUT = httpx.Timeout(10.0)
_ISSUES_PATH = "/rest/v1/accessibility_issues"


class SupabaseAccessibilityIssueRepository:
    """CRUD for accessibility issues against the Supabase PostgREST endpoint."""

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
    def _row_to_issue(row: Dict[str, Any]) -> StoredAccessibilityIssue:
        return StoredAccessibilityIssue(
            id=str(row["id"]),
            scan_id=str(row["scan_id"]),
            rule_id=str(row["rule_id"]),
            rule_name=str(row["rule_name"]),
            description=str(row.get("description") or ""),
            help=str(row.get("help") or ""),
            help_url=str(row.get("help_url") or ""),
            impact=Impact(row["impact"]),
            wcag_level=WcagLevel(row["wcag_level"]) if row.get("wcag_level") else None,
            tags=list(row.get("tags") or []),
            element_selector=str(row.get("element_selector") or ""),
            html_snippet=str(row.get("html_snippet") or ""),
            failure_summary=str(row.get("failure_summary") or ""),
            xpath=str(row.get("xpath") or ""),
            css_path=str(row.get("css_path") or ""),
            dom_path=str(row.get("dom_path") or ""),
            screenshot_path=str(row.get("screenshot_path") or ""),
            created_at=_parse_iso(row["created_at"]),
        )

    # --- AccessibilityIssueRepository --------------------------------------

    async def insert_many(self, scan_id: str, issues: List[AccessibilityIssue]) -> int:
        self._require_config()
        if not issues:
            return 0
        rows = [
            {"scan_id": scan_id, **issue.model_dump(mode="json")}
            for issue in issues
        ]
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}{_ISSUES_PATH}",
                headers=self._headers(),
                json=rows,
            )
        self._raise_for_status(response, "insert accessibility issues")
        return len(rows)

    async def list_for_scan(self, user_id: str, scan_id: str) -> List[StoredAccessibilityIssue]:
        self._require_config()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{self._base_url}{_ISSUES_PATH}",
                headers=self._headers(),
                params={
                    "scan_id": f"eq.{scan_id}",
                    "scans.user_id": f"eq.{user_id}",
                    "select": "*,scans!inner(user_id)",
                    "order": "created_at.asc",
                },
            )
        self._raise_for_status(response, "list accessibility issues")
        return [self._row_to_issue(row) for row in response.json()]


_FRACTIONAL_SECONDS = re.compile(r"\.(\d+)([+-]|$)")


def _parse_iso(value: str) -> datetime:
    """Parse a PostgREST ISO-8601 timestamp (``Z`` or ``+00:00`` suffix).

    PostgREST trims trailing zeros in fractional seconds (``.874710`` →
    ``.87471``); pad back to 6 digits so ``fromisoformat`` accepts it.
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
