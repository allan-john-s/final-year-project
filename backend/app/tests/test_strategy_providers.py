"""Tests for the strategy generation providers (Module 4).

Covers the factory dispatch (mock / openai-without-key / unknown → graceful
503), the deterministic context-aware mock provider, and the OpenAI-compatible
client's sanitized failure paths (timeout, rate limit, upstream error, invalid
JSON, unexpected shapes) — all with a stubbed HTTP client, no network, no key.
"""

import json

import httpx
import pytest

from app.core.config import Settings
from app.strategies.exceptions import (
    StrategyConfigurationError,
    StrategyOutputError,
    StrategyProviderError,
)
from app.strategies.models import (
    StrategyGenerationRequest,
    StrategyTarget,
)
from app.strategies.providers import (
    MockStrategyProvider,
    OpenAIStrategyProvider,
    create_provider,
)
from app.strategies.providers.openai import _extract_json_array
from app.tests.test_strategy_prompts import build_context

mock_settings = Settings(
    llm_provider="mock", llm_model="mock-model", llm_api_key=""
)


def make_request(count: int = 3) -> StrategyGenerationRequest:
    context = build_context()
    issue = context.issues[0]
    target = StrategyTarget(
        target_type="issue", issue_id=issue.issue_id, issues=[issue]
    )
    return StrategyGenerationRequest(
        prompt_version="1.0",
        context_version=context.context_version,
        system_prompt="system",
        user_prompt="user",
        target=target,
        model="mock-model",
        temperature=0.2,
        max_tokens=1000,
        strategy_count=count,
    )


# --- factory ----------------------------------------------------------------


def test_factory_returns_mock_provider() -> None:
    provider = create_provider(mock_settings)
    assert isinstance(provider, MockStrategyProvider)
    assert provider.name == "mock"


def test_factory_openai_without_key_fails_gracefully() -> None:
    with pytest.raises(StrategyConfigurationError) as excinfo:
        create_provider(Settings(llm_provider="openai", llm_api_key=""))
    assert "LLM_API_KEY" in str(excinfo.value)
    assert excinfo.value.status_code == 503


def test_factory_unknown_provider_fails_gracefully() -> None:
    with pytest.raises(StrategyConfigurationError) as excinfo:
        create_provider(Settings(llm_provider="claude", llm_api_key="x"))
    assert excinfo.value.status_code == 503


# --- mock provider ----------------------------------------------------------


def test_mock_provider_returns_requested_count() -> None:
    for count in (2, 3, 5):
        provider = MockStrategyProvider(mock_settings)
        strategies = _run(provider.generate(make_request(count)))
        assert len(strategies) == count


def test_mock_provider_is_deterministic() -> None:
    """The same request always yields byte-identical strategies."""
    provider = MockStrategyProvider(mock_settings)
    request = make_request(3)
    first = _run(provider.generate(request))
    second = _run(provider.generate(request))
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]


def test_mock_provider_is_context_aware_and_distinct() -> None:
    context = build_context()
    issue = context.issues[0]
    target = StrategyTarget(
        target_type="issue", issue_id=issue.issue_id, issues=[issue]
    )
    request = make_request(3)
    request.target = target
    strategies = _run(MockStrategyProvider(mock_settings).generate(request))

    titles = [s.title for s in strategies]
    assert len(set(titles)) == 3  # genuinely distinct
    types = {s.strategy_type for s in strategies}
    assert len(types) >= 2  # different strategy families
    for strategy in strategies:
        combined = (
            strategy.title + " " + strategy.summary + " " + strategy.rationale
        )
        assert issue.rule.rule_id in combined  # real rule referenced
        assert issue.wcag.criteria  # criteria preserved
        assert strategy.wcag_alignment == sorted(set(issue.wcag.criteria))
        assert strategy.evidence_reference == issue.issue_id
        assert 0.0 <= strategy.confidence <= 1.0
        assert strategy.implementation_steps


def test_mock_provider_group_target_references_group() -> None:
    context = build_context()
    group = next(g for g in context.groups if g.group_type == "same_rule")
    members = [i for i in context.issues if i.issue_id in group.issue_ids]
    target = StrategyTarget(
        target_type="group", group_id=group.group_id, issues=members
    )
    request = make_request(3)
    request.target = target
    strategies = _run(MockStrategyProvider(mock_settings).generate(request))

    assert len(strategies) == 3
    assert all(s.group_id == group.group_id for s in strategies)
    assert all(s.evidence_reference == group.group_id for s in strategies)


# --- OpenAI-compatible provider ---------------------------------------------


class FakeResponse:
    def __init__(self, status_code: int = 200, json_data=None) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "http://provider.test"),
                response=self,
            )

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, *, response=None, error=None) -> None:
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


def _openai_settings(**overrides) -> Settings:
    defaults = {
        "llm_provider": "openai",
        "llm_api_key": "sk-test-not-real",
        "llm_base_url": "https://provider.test/v1",
        "llm_model": "gpt-test",
        "llm_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request() -> StrategyGenerationRequest:
    return StrategyGenerationRequest(
        prompt_version="1.0",
        context_version="1.0",
        system_prompt="sys",
        user_prompt="user",
        target=StrategyTarget(target_type="issue", issues=[]),
        model="gpt-test",
        temperature=0.2,
        max_tokens=1000,
        strategy_count=3,
    )


def _valid_strategies_json(count: int = 3, fenced: bool = False) -> str:
    items = []
    for i in range(1, count + 1):
        items.append(
            {
                "strategy_id": f"native-{i}",
                "strategy_index": i,
                "issue_id": "issue-1",
                "context_version": "1.0",
                "strategy_type": "native_html",
                "title": f"Native strategy {i}",
                "summary": f"Summary {i}",
                "rationale": f"Rationale {i}",
                "implementation_steps": [f"Step {i}"],
                "expected_accessibility_impact": "high",
                "implementation_effort": "low",
                "wcag_alignment": ["1.4.3"],
                "risks": [],
                "assumptions": [],
                "confidence": 0.8,
            }
        )
    payload = json.dumps(items)
    return f"```json\n{payload}\n```" if fenced else payload


def _completion_response(content: str) -> FakeResponse:
    return FakeResponse(json_data={"choices": [{"message": {"content": content}}]})


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_openai_provider_parses_valid_response(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response(_valid_strategies_json(3)))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    strategies = _run(provider.generate(_request()))

    assert len(strategies) == 3
    assert strategies[0].strategy_id == "native-1"


def test_openai_provider_parses_fenced_response(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response(_valid_strategies_json(2, fenced=True)))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    strategies = _run(provider.generate(_request()))

    assert len(strategies) == 2


def test_openai_provider_rejects_invalid_json(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response("not json at all"))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyOutputError):
        _run(provider.generate(_request()))


def test_openai_provider_rejects_non_array_json(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response('{"strategies": []}'))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyOutputError):
        _run(provider.generate(_request()))


def test_openai_provider_rejects_schema_mismatch(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    bad = json.dumps([{"strategy_id": "x", "title": 42, "summary": "s"}])
    fake = FakeAsyncClient(response=_completion_response(bad))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyOutputError):
        _run(provider.generate(_request()))


def test_openai_provider_timeout_is_sanitized(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(error=httpx.TimeoutException("read timeout after 5s"))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyProviderError) as excinfo:
        _run(provider.generate(_request()))
    assert "timed out" in str(excinfo.value)
    assert "5s" not in str(excinfo.value)  # raw detail not leaked


def test_openai_provider_rate_limit_is_sanitized(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(status_code=429, json_data={}))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyProviderError) as excinfo:
        _run(provider.generate(_request()))
    assert "rate-limited" in str(excinfo.value)


def test_openai_provider_upstream_error_is_sanitized(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(status_code=500, json_data={"error": "kaboom"}))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyProviderError) as excinfo:
        _run(provider.generate(_request()))
    assert "kaboom" not in str(excinfo.value)


def test_openai_provider_unexpected_shape_is_sanitized(monkeypatch) -> None:
    provider = OpenAIStrategyProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(json_data={"choices": []}))
    monkeypatch.setattr("app.strategies.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(StrategyOutputError):
        _run(provider.generate(_request()))


def test_extract_json_array_handles_fences_and_prose() -> None:
    assert _extract_json_array("[1,2,3]") == [1, 2, 3]
    assert _extract_json_array("Here you go:\n[1,2,3]\n\nDone.") == [1, 2, 3]
    assert _extract_json_array('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    with pytest.raises(StrategyOutputError):
        _extract_json_array("no array here")
