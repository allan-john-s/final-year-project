"""Tests for the evaluation providers (Module 5).

Covers the factory dispatch (mock / openai-without-key / unknown → graceful
503), the deterministic context-aware mock evaluator (score semantics,
determinism, evidence references), and the OpenAI-compatible client's
sanitized failure paths — all with a stubbed HTTP client, no network, no key.
"""

import json

import httpx
import pytest

from app.core.config import Settings
from app.evaluations.exceptions import (
    EvaluationConfigurationError,
    EvaluationOutputError,
    EvaluationProviderError,
)
from app.evaluations.models import StrategyEvaluationRequest
from app.evaluations.providers import (
    MockEvaluationProvider,
    OpenAIEvaluationProvider,
    create_provider,
)
from app.evaluations.providers.openai import _extract_json_object
from app.strategies.models import CandidateStrategy, StrategyTarget
from app.tests.test_strategy_models import make_strategy
from app.tests.test_strategy_prompts import build_context

mock_settings = Settings(
    llm_provider="mock", llm_model="mock-model", llm_api_key=""
)


def make_request(**overrides) -> StrategyEvaluationRequest:
    context = build_context()
    issue = context.issues[0]
    target = StrategyTarget(
        target_type="issue", issue_id=issue.issue_id, issues=[issue]
    )
    strategy = CandidateStrategy.model_validate(
        make_strategy(strategy_id="native-1", issue_id=issue.issue_id)
    )
    defaults = {
        "prompt_version": "1.0",
        "evaluation_version": "1.0",
        "context_version": context.context_version,
        "system_prompt": "system",
        "user_prompt": "user",
        "strategy": strategy,
        "target": target,
        "model": "mock-model",
        "temperature": 0.2,
        "max_tokens": 1000,
    }
    defaults.update(overrides)
    return StrategyEvaluationRequest(**defaults)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# --- factory ----------------------------------------------------------------


def test_factory_returns_mock_provider() -> None:
    provider = create_provider(mock_settings)
    assert isinstance(provider, MockEvaluationProvider)
    assert provider.name == "mock"


def test_factory_openai_without_key_fails_gracefully() -> None:
    with pytest.raises(EvaluationConfigurationError) as excinfo:
        create_provider(Settings(llm_provider="openai", llm_api_key=""))
    assert "LLM_API_KEY" in str(excinfo.value)
    assert excinfo.value.status_code == 503


def test_factory_unknown_provider_fails_gracefully() -> None:
    with pytest.raises(EvaluationConfigurationError) as excinfo:
        create_provider(Settings(llm_provider="claude", llm_api_key="x"))
    assert excinfo.value.status_code == 503


# --- mock provider ----------------------------------------------------------


def test_mock_provider_is_deterministic() -> None:
    """The same request always yields byte-identical evaluations."""
    provider = MockEvaluationProvider(mock_settings)
    request = make_request()
    first = _run(provider.evaluate(request))
    second = _run(provider.evaluate(request))
    assert first.model_dump() == second.model_dump()


def test_mock_provider_scores_follow_semantics() -> None:
    """Native HTML is high-impact/easy; behavioral is harder; ARIA is a
    fallback with lower maintainability."""
    provider = MockEvaluationProvider(mock_settings)
    context = build_context()
    issue = context.issues[0]

    strategies = {
        "native": CandidateStrategy.model_validate(
            make_strategy(strategy_id="native-1", issue_id=issue.issue_id, strategy_type="native_html")
        ),
        "aria": CandidateStrategy.model_validate(
            make_strategy(strategy_id="aria-1", issue_id=issue.issue_id, strategy_type="aria")
        ),
        "behavioral": CandidateStrategy.model_validate(
            make_strategy(strategy_id="beh-1", issue_id=issue.issue_id, strategy_type="behavioral")
        ),
    }

    native = _run(
        provider.evaluate(
            make_request(strategy=strategies["native"])
        )
    )
    aria = _run(provider.evaluate(make_request(strategy=strategies["aria"])))
    behavioral = _run(
        provider.evaluate(make_request(strategy=strategies["behavioral"]))
    )

    # Positive criteria: native >= 8; effort: native easier than behavioral;
    # risk: native lower-risk than behavioral.
    assert native.accessibility_impact_score >= 8
    assert native.standards_compliance_score >= 8
    assert native.implementation_effort_score > behavioral.implementation_effort_score
    assert native.risk_score > behavioral.risk_score
    # ARIA is a fallback: lower maintainability than native.
    assert aria.maintainability_score < native.maintainability_score
    # All scores bounded.
    for draft in (native, aria, behavioral):
        for field in (
            "accessibility_impact_score",
            "standards_compliance_score",
            "contextual_suitability_score",
            "implementation_effort_score",
            "maintainability_score",
            "compatibility_score",
            "risk_score",
        ):
            assert 0 <= getattr(draft, field) <= 10


def test_mock_provider_is_context_aware() -> None:
    provider = MockEvaluationProvider(mock_settings)
    context = build_context()
    issue = next(i for i in context.issues if i.rule.rule_id == "color-contrast")
    strategy = CandidateStrategy.model_validate(
        make_strategy(
            strategy_id="native-1",
            issue_id=issue.issue_id,
            evidence_reference=issue.issue_id,
        )
    )
    draft = _run(
        provider.evaluate(
            make_request(
                strategy=strategy,
                target=StrategyTarget(
                    target_type="issue", issue_id=issue.issue_id, issues=[issue]
                ),
            )
        )
    )

    combined = " ".join(draft.strengths + draft.weaknesses + [draft.rationale])
    assert issue.rule.rule_id in combined  # color-contrast referenced
    assert issue.element.selector in combined  # #main > p referenced
    assert draft.evidence_references == [issue.issue_id]
    assert "screen-reader" in " ".join(draft.uncertainties).lower()


def test_mock_provider_aria_adjustment_when_aria_present() -> None:
    provider = MockEvaluationProvider(mock_settings)
    context = build_context()
    issue = next(i for i in context.issues if i.rule.rule_id == "color-contrast")
    aria_issue = issue.model_copy(deep=True)
    aria_issue.element = aria_issue.element.model_copy(
        update={"aria": {"aria-label": "text"}}
    )
    strategy = CandidateStrategy.model_validate(
        make_strategy(strategy_id="aria-1", issue_id=issue.issue_id, strategy_type="aria")
    )

    plain = _run(
        provider.evaluate(
            make_request(
                strategy=strategy,
                target=StrategyTarget(
                    target_type="issue", issue_id=issue.issue_id, issues=[issue]
                ),
            )
        )
    )
    with_aria = _run(
        provider.evaluate(
            make_request(
                strategy=strategy,
                target=StrategyTarget(
                    target_type="issue", issue_id=issue.issue_id, issues=[aria_issue]
                ),
            )
        )
    )

    assert with_aria.contextual_suitability_score == plain.contextual_suitability_score + 1


def test_mock_provider_requires_issue_evidence() -> None:
    provider = MockEvaluationProvider(mock_settings)
    strategy = CandidateStrategy.model_validate(
        make_strategy(strategy_id="native-1")
    )
    request = make_request(
        strategy=strategy,
        target=StrategyTarget(target_type="issue", issue_id="x", issues=[]),
    )

    with pytest.raises(EvaluationOutputError):
        _run(provider.evaluate(request))


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


def _valid_draft_json(fenced: bool = False) -> str:
    payload = json.dumps(
        {
            "strategy_id": "native-1",
            "accessibility_impact_score": 9,
            "standards_compliance_score": 9,
            "contextual_suitability_score": 8,
            "implementation_effort_score": 8,
            "maintainability_score": 9,
            "compatibility_score": 9,
            "risk_score": 8,
            "strengths": ["Native semantics are robust."],
            "weaknesses": ["Styling may change."],
            "rationale": "Native HTML is the most robust fix.",
            "assumptions": ["Source is editable."],
            "uncertainties": ["Manual check still required."],
            "evidence_references": ["issue-1"],
        }
    )
    return f"```json\n{payload}\n```" if fenced else payload


def _completion_response(content: str) -> FakeResponse:
    return FakeResponse(json_data={"choices": [{"message": {"content": content}}]})


def test_openai_provider_parses_valid_response(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response(_valid_draft_json()))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    draft = _run(provider.evaluate(make_request()))

    assert draft.strategy_id == "native-1"
    assert draft.accessibility_impact_score == 9
    assert draft.evidence_references == ["issue-1"]


def test_openai_provider_parses_fenced_response(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response(_valid_draft_json(fenced=True)))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    draft = _run(provider.evaluate(make_request()))

    assert draft.strategy_id == "native-1"


def test_openai_provider_rejects_invalid_json(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response("not json at all"))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationOutputError):
        _run(provider.evaluate(make_request()))


def test_openai_provider_rejects_non_object_json(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=_completion_response("[1, 2, 3]"))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationOutputError):
        _run(provider.evaluate(make_request()))


def test_openai_provider_rejects_schema_mismatch(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    bad = json.dumps({"strategy_id": "native-1", "accessibility_impact_score": 42})
    fake = FakeAsyncClient(response=_completion_response(bad))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationOutputError):
        _run(provider.evaluate(make_request()))


def test_openai_provider_timeout_is_sanitized(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(error=httpx.TimeoutException("read timeout after 5s"))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationProviderError) as excinfo:
        _run(provider.evaluate(make_request()))
    assert "timed out" in str(excinfo.value)
    assert "5s" not in str(excinfo.value)  # raw detail not leaked


def test_openai_provider_rate_limit_is_sanitized(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(status_code=429, json_data={}))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationProviderError) as excinfo:
        _run(provider.evaluate(make_request()))
    assert "rate-limited" in str(excinfo.value)


def test_openai_provider_upstream_error_is_sanitized(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(status_code=500, json_data={"error": "kaboom"}))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationProviderError) as excinfo:
        _run(provider.evaluate(make_request()))
    assert "kaboom" not in str(excinfo.value)


def test_openai_provider_unexpected_shape_is_sanitized(monkeypatch) -> None:
    provider = OpenAIEvaluationProvider(_openai_settings())
    fake = FakeAsyncClient(response=FakeResponse(json_data={"choices": []}))
    monkeypatch.setattr("app.evaluations.providers.openai.httpx.AsyncClient", lambda timeout: fake)

    with pytest.raises(EvaluationOutputError):
        _run(provider.evaluate(make_request()))


def test_extract_json_object_handles_fences_and_prose() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('Here you go:\n{"a": 1}\n\nDone.') == {"a": 1}
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(EvaluationOutputError):
        _extract_json_object("no object here")
    with pytest.raises(EvaluationOutputError):
        _extract_json_object("[1, 2, 3]")
