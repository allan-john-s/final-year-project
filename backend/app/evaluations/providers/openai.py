"""OpenAI-compatible strategy evaluation provider.

Talks to any ``/chat/completions`` endpoint (OpenAI, Azure OpenAI, local
gateways) over HTTP with the versioned evaluation prompts built by
:mod:`app.evaluations.prompts`. The API key lives only in the request
``Authorization`` header — never in logs, exceptions, or responses.

Failure handling is sanitized: timeouts, rate limits and network errors
surface as :class:`EvaluationProviderError`; responses that do not parse into
:class:`EvaluationDraft` objects surface as :class:`EvaluationOutputError`.
Raw provider bodies are never echoed to clients.
"""

import json

import httpx

from app.core.config import Settings
from app.evaluations.exceptions import EvaluationOutputError, EvaluationProviderError
from app.evaluations.models import EvaluationDraft, StrategyEvaluationRequest


class OpenAIEvaluationProvider:
    """A stateless chat-completions evaluator (one request per call)."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = settings.llm_timeout_seconds

    async def evaluate(
        self, request: StrategyEvaluationRequest
    ) -> EvaluationDraft:
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._settings.llm_api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise EvaluationProviderError(
                "The evaluation provider timed out."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise EvaluationProviderError(
                    "The evaluation provider is rate-limited; please try "
                    "again later."
                ) from exc
            raise EvaluationProviderError(
                "The evaluation provider returned an error."
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise EvaluationProviderError(
                "The evaluation provider is unavailable."
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EvaluationOutputError(
                "The evaluation provider returned an unexpected response shape."
            ) from exc

        raw_item = _extract_json_object(content)
        try:
            return EvaluationDraft.model_validate(raw_item)
        except Exception as exc:
            raise EvaluationOutputError(
                "The evaluation provider returned output that does not match "
                "the expected schema."
            ) from exc


def _extract_json_object(content: str) -> dict:
    """Tolerantly extract a single JSON object from a completion.

    Handles optional code fences and stray prose around the object. Returns
    the parsed dict; raises :class:`EvaluationOutputError` if none exists.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lstrip("`").strip().lower() in ("json", ""):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise EvaluationOutputError(
            "The evaluation provider response did not contain a JSON object."
        )
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise EvaluationOutputError(
            "The evaluation provider response contained invalid JSON."
        ) from exc
    if not isinstance(parsed, dict):
        raise EvaluationOutputError(
            "The evaluation provider response was not a JSON object."
        )
    return parsed
