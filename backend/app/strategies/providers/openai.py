"""OpenAI-compatible strategy generation provider.

Talks to any ``/chat/completions`` endpoint (OpenAI, Azure OpenAI, local
gateways) over HTTP with the versioned prompts built by
:mod:`app.strategies.prompts`. The API key lives only in the request
``Authorization`` header — never in logs, exceptions, or responses.

Failure handling is sanitized: timeouts, rate limits and network errors
surface as :class:`StrategyProviderError`; responses that do not parse into
:class:`CandidateStrategy` objects surface as :class:`StrategyOutputError`.
Raw provider bodies are never echoed to clients.
"""

import json
from typing import List

import httpx

from app.core.config import Settings
from app.strategies.exceptions import StrategyOutputError, StrategyProviderError
from app.strategies.models import CandidateStrategy, StrategyGenerationRequest


class OpenAIStrategyProvider:
    """A stateless chat-completions client (one request per call)."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = settings.llm_timeout_seconds

    async def generate(
        self, request: StrategyGenerationRequest
    ) -> List[CandidateStrategy]:
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
            raise StrategyProviderError(
                "The language model provider timed out."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise StrategyProviderError(
                    "The language model provider is rate-limited; please try "
                    "again later."
                ) from exc
            raise StrategyProviderError(
                "The language model provider returned an error."
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise StrategyProviderError(
                "The language model provider is unavailable."
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise StrategyOutputError(
                "The provider returned an unexpected response shape."
            ) from exc

        raw_items = _extract_json_array(content)
        try:
            strategies = [
                CandidateStrategy.model_validate(item) for item in raw_items
            ]
        except Exception as exc:
            raise StrategyOutputError(
                "The provider returned strategies that do not match the "
                "expected schema."
            ) from exc

        if not strategies:
            raise StrategyOutputError("The provider returned no strategies.")
        return strategies


def _extract_json_array(content: str) -> list:
    """Tolerantly extract a JSON array from a completion.

    Handles optional code fences and stray prose around the array. Returns
    the parsed list; raises :class:`StrategyOutputError` if none exists.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        # Strip a ```json ... ``` fence if present.
        lines = text.splitlines()
        if lines and lines[0].strip().lstrip("`").strip().lower() in ("json", ""):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise StrategyOutputError(
            "The provider response did not contain a JSON array."
        )
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise StrategyOutputError(
            "The provider response contained invalid JSON."
        ) from exc
    if not isinstance(parsed, list):
        raise StrategyOutputError(
            "The provider response was not a JSON array of strategies."
        )
    return parsed
