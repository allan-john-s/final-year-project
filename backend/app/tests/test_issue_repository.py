"""Tests for the Supabase PostgREST accessibility issue repository.

The PostgREST HTTP calls are replaced with a fake transport (same convention
as the scan/project repository tests) so the repository is exercised without
network access or real credentials.
"""

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.repositories.issues import SupabaseAccessibilityIssueRepository
from app.scans.exceptions import ScanConfigurationError, ScanError
from app.scans.models import StoredAccessibilityIssue
from app.scanners.models import AccessibilityIssue, Impact, WcagLevel

ROW = {
    "id": "issue-1",
    "scan_id": "scan-1",
    "rule_id": "color-contrast",
    "rule_name": "Elements must have sufficient color contrast",
    "description": "Ensures contrast meets WCAG 2 AA thresholds",
    "help": "Elements must have sufficient color contrast",
    "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
    "impact": "SERIOUS",
    "wcag_level": "AA",
    "tags": ["wcag2aa", "wcag143"],
    "element_selector": "#main > p",
    "html_snippet": "<p>Low contrast</p>",
    "failure_summary": "Fix any of the following: insufficient contrast",
    "xpath": "",
    "css_path": "",
    "dom_path": "#main > p",
    "screenshot_path": "",
    "created_at": "2026-08-14T10:00:00+00:00",
}


def make_issue(**overrides) -> AccessibilityIssue:
    defaults = {
        "rule_id": "color-contrast",
        "rule_name": "Elements must have sufficient color contrast",
        "impact": Impact.SERIOUS,
        "wcag_level": WcagLevel.AA,
        "tags": ["wcag2aa"],
        "element_selector": "#main > p",
        "html_snippet": "<p>Low contrast</p>",
    }
    defaults.update(overrides)
    return AccessibilityIssue(**defaults)


def _settings(**overrides) -> Settings:
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "service-role-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _repo(**settings_overrides) -> SupabaseAccessibilityIssueRepository:
    return SupabaseAccessibilityIssueRepository(_settings(**settings_overrides))


class FakeResponse:
    def __init__(self, status_code: int, json_data) -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


class FakeAsyncClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)


def _patch_http(monkeypatch, *responses) -> FakeAsyncClient:
    client = FakeAsyncClient(responses)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    return client


def test_insert_many_posts_rows_with_scan_id(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(201, []))

    count = asyncio.run(repo.insert_many("scan-1", [make_issue(), make_issue(impact=Impact.MINOR)]))

    assert count == 2
    method, url, kwargs = client.calls[0]
    assert method == "post"
    assert url == "https://example.supabase.co/rest/v1/accessibility_issues"
    assert kwargs["headers"]["apikey"] == "service-role-key"
    rows = kwargs["json"]
    assert len(rows) == 2
    assert rows[0]["scan_id"] == "scan-1"
    assert rows[0]["rule_id"] == "color-contrast"
    assert rows[0]["impact"] == "SERIOUS"  # enum serialized to its value
    assert rows[0]["wcag_level"] == "AA"
    assert rows[0]["tags"] == ["wcag2aa"]
    assert rows[1]["impact"] == "MINOR"
    # No ownership/id fields sneak into the payload.
    assert "user_id" not in rows[0]
    assert "id" not in rows[0]


def test_insert_many_empty_list_skips_network(monkeypatch) -> None:
    repo = _repo()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("no network"))

    count = asyncio.run(repo.insert_many("scan-1", []))

    assert count == 0


def test_list_for_scan_scopes_query_to_owner_via_inner_join(monkeypatch) -> None:
    repo = _repo()
    client = _patch_http(monkeypatch, FakeResponse(200, [ROW]))

    issues = asyncio.run(repo.list_for_scan("user-a", "scan-1"))

    method, url, kwargs = client.calls[0]
    assert method == "get"
    params = kwargs["params"]
    assert params["scan_id"] == "eq.scan-1"
    assert params["scans.user_id"] == "eq.user-a"
    assert params["select"] == "*,scans!inner(user_id)"
    assert params["order"] == "created_at.asc"

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, StoredAccessibilityIssue)
    assert issue.id == "issue-1"
    assert issue.scan_id == "scan-1"
    assert issue.impact is Impact.SERIOUS
    assert issue.wcag_level is WcagLevel.AA
    assert issue.tags == ["wcag2aa", "wcag143"]
    assert issue.created_at is not None


def test_list_for_scan_maps_nullable_fields(monkeypatch) -> None:
    repo = _repo()
    row = {**ROW, "wcag_level": None, "tags": None, "impact": "MINOR"}
    _patch_http(monkeypatch, FakeResponse(200, [row]))

    issues = asyncio.run(repo.list_for_scan("user-a", "scan-1"))

    assert issues[0].wcag_level is None
    assert issues[0].tags == []
    assert issues[0].impact is Impact.MINOR


def test_repository_requires_configuration_before_network(monkeypatch) -> None:
    repo = _repo(supabase_url="", supabase_service_role_key="")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("no network"))

    with pytest.raises(ScanConfigurationError):
        asyncio.run(repo.insert_many("scan-1", [make_issue()]))
    with pytest.raises(ScanConfigurationError):
        asyncio.run(repo.list_for_scan("user-a", "scan-1"))


def test_repository_maps_postgrest_errors(monkeypatch) -> None:
    repo = _repo()
    _patch_http(
        monkeypatch,
        FakeResponse(400, {"code": "PGRST200", "message": "Could not parse the request body"}),
    )

    with pytest.raises(ScanError) as excinfo:
        asyncio.run(repo.insert_many("scan-1", [make_issue()]))

    assert "Could not parse the request body" in str(excinfo.value)
    assert "service-role-key" not in str(excinfo.value)
