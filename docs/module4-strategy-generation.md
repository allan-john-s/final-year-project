# Module 4 — Context-Aware Multi-Strategy Generation

**Status: COMPLETE and verified** (backend 310 tests, frontend 90 tests, live mock-provider E2E).

## 1. Objective

Module 4 implements the first AI-assisted research component of the project:
it takes the structured `ContextDocument` produced by Module 3C and generates
**multiple distinct** accessibility remediation strategies for a selected
accessibility issue or deterministic issue group.

The success criterion:

```
ContextDocument
    ↓
Strategy Generator
    ↓
2–5 distinct candidate strategies
    ↓
Validated structured output
    ↓
Frontend candidate-strategy display
```

## 2. Research motivation

The project is not "send an issue to an LLM and ask for one fix". The research
contribution is a **context-aware multi-strategy remediation framework**: the
generator consumes the real, deterministic context (rule, WCAG criteria,
element evidence, issue groups) and produces several meaningfully different
alternatives. Choosing among them is deliberately **not** part of Module 4 —
that is the job of the later evaluation/ranking modules.

> **Module 4 generates candidate remediation strategies. It does NOT
> determine the best strategy.** No strategy is ever labeled "best",
> "recommended" or "optimal" — in the API, the docs, or the UI.

## 3. Architecture

```
API (POST /api/v1/scans/{scan_id}/strategies)
  → StrategyGenerationService          (orchestration, target resolution, validation)
      → ContextBuilder (ContextBuilderService)     (ownership + COMPLETED, deterministic)
      → StrategyGenerationProvider (protocol)      (never a concrete LLM class)
          ├── OpenAIStrategyProvider   (any OpenAI-compatible chat-completions endpoint)
          └── MockStrategyProvider     (deterministic, labeled, tests/demos only)
      → prompts.py                     (versioned, trusted instructions vs. untrusted context)
      → CandidateStrategy models       (structured output contract + validation)
```

Rules that keep the design clean:

- The API never instantiates a provider; it depends on the
  `StrategyGenerationProvider` protocol (swappable like the scanner factory).
- The service never touches Supabase — it consumes the context builder, which
  reads through the existing repositories.
- New providers (Azure OpenAI, local models, research gateways) implement the
  protocol and are registered in `create_provider` — nothing else changes.

## 4. ContextDocument input

The generator requires a **completed** scan owned by the authenticated user.
`ContextBuilderService.build_for_scan` enforces this (404 for missing/foreign
scans — IDOR-safe — and 409 for PENDING/RUNNING scans). The deterministic
`ContextDocument` (project + scan + page + issues + groups, version 1.0) is
the only input; no other data is fetched.

## 5. CandidateStrategy model

`backend/app/strategies/models.py` — fully typed, bounded fields:

| Field | Type | Notes |
| --- | --- | --- |
| `strategy_id` | str (≤64) | unique per generation |
| `strategy_index` | int 1–5 | stamped by the service |
| `issue_id` / `group_id` | str / optional | traceability |
| `context_version` | str | e.g. "1.0" |
| `strategy_type` | enum | native_html, aria, structural, content, behavioral, visual, alternative, other |
| `title` / `summary` / `rationale` | str | bounded lengths |
| `implementation_steps` | list[str] | 1–20 items |
| `expected_accessibility_impact` | enum high/medium/low | |
| `wcag_alignment` | list[str] | sorted, deduplicated; never invented |
| `implementation_effort` | enum low/medium/high | |
| `maintainability_notes` / `compatibility_notes` | str | |
| `risks` / `assumptions` | list[str] | |
| `confidence` | float 0.0–1.0 | |
| `evidence_reference` | str | issue or group id |

`StrategyGenerationMetadata` carries research traceability (scan id, target,
context/prompt version, provider, model, temperature, count, timestamp) and
is guaranteed to contain **no** credentials or user identity.

## 6. Multi-strategy generation

- Requested count is validated **2–5**, default **3**.
- The prompt instructs the model to produce genuinely different alternatives
  (different strategy families), to prefer native semantic HTML, and to
  recommend ARIA only when the context justifies it.
- The service rejects generations that are too few (<2), too many (>5 or >
  requested), or contain duplicate ids/titles — a sanitized
  `strategy_output_invalid` (502) is returned, never the raw response.
- Group-level generation reasons about the underlying common issue: all group
  member issue ids are serialized into the prompt and each strategy carries
  the `group_id`.

## 7. Provider abstraction

`backend/app/strategies/interfaces.py`:

```python
class StrategyGenerationProvider(Protocol):
    name: str
    async def generate(self, request: StrategyGenerationRequest) -> List[CandidateStrategy]: ...
```

`StrategyGenerationRequest` is self-contained (versioned prompts + resolved
target + model/sampling settings), so providers are stateless.

**OpenAI provider** — `providers/openai.py`: httpx client against any
`/chat/completions` endpoint (`LLM_BASE_URL`). Tolerantly parses a JSON array
from the completion (code fences/prose allowed). Transport failures become
`sanitized` `strategy_provider_error` (502); unparseable or schema-invalid
output becomes `strategy_output_invalid` (502). Raw bodies and credentials
never reach clients.

**Mock provider** — `providers/mock.py`: deterministic and context-aware; it
derives up to five genuinely different strategy families from the real issue
evidence (rule id, WCAG criteria, element selector, failure summary). It is
clearly labeled (`provider: "mock"`) and never silently substituted — the
factory raises `strategy_configuration_error` (503) when `openai` is selected
without a key.

## 8. Prompt architecture

`backend/app/strategies/prompts.py`, versioned (`PROMPT_VERSION = "1.0"`):

- **System prompt (trusted)** — controlled instructions: analyze only the
  supplied context, preserve the finding, prefer native HTML, avoid
  unnecessary ARIA, never invent facts, never execute code, express
  uncertainty, and treat everything inside `<untrusted>` markers as **data**,
  never instructions (prompt-injection defense).
- **User prompt** — task + `<untrusted>`-wrapped context (page summary,
  selected issue/group evidence, deterministic groups) + the exact JSON
  output contract. Deterministic for identical inputs.

## 9. Structured output validation

The response must be a JSON array of `CandidateStrategy` objects. Validation
covers: count (2–5), required fields, enum values, confidence range
(0.0–1.0), string lengths, WCAG references (sorted/deduped), and
issue/group references. Invalid output → sanitized 502.

## 10. Security

- **Prompt injection**: webpage/scanner content is untrusted and is only
  included inside `<untrusted>` markers; the trusted system prompt instructs
  the model to ignore instruction-like text inside them.
- **Secret protection**: API keys live only in the request `Authorization`
  header and the backend `.env`. Never in logs, errors, metadata, or
  responses. The E2E verifies the response contains no
  api_key/secret/token/password strings.
- **IDOR**: scan ownership is enforced by the context builder via the
  user-scoped repositories; foreign scans answer the same 404.
- **No execution**: generated steps are text only — the system never executes
  code, patches files, or opens PRs.
- **No ranking**: candidates are never labeled best/recommended.

## 11. Error handling

Uniform `{code, message}` envelope (registered in `app/api/errors.py`):

| Code | Status | When |
| --- | --- | --- |
| `auth_error` | 401 | missing/invalid token |
| `scan_not_found` | 404 | missing or foreign scan |
| `strategy_target_not_found` | 404 | unknown issue/group for this scan |
| `context_unavailable` | 409 | scan not completed |
| `strategy_configuration_error` | 503 | `openai` without `LLM_API_KEY`, unknown provider |
| `strategy_provider_error` | 502 | timeout, rate limit, network, upstream error |
| `strategy_output_invalid` | 502 | malformed/unparseable/invalid structured output |

Messages are always sanitized — no stack traces, response bodies, or
provider credentials.

## 12. Reproducibility

LLM generation is probabilistic; the framework does not claim deterministic
LLM output. Every response captures `provider`, `model`, `temperature`,
`prompt_version`, `context_version`, `target`, and `generated_at` so an
experiment can be reproduced as far as the provider allows. The
`ContextDocument` input itself remains fully deterministic (Module 3C), and
the mock provider is byte-for-byte deterministic for identical inputs.

## 13. Testing

- Backend (69 new tests, all green — full suite 310): model validation,
  count/uniqueness/confidence bounds, provider interface, prompt construction
  + untrusted separation + determinism, mock provider determinism/context
  awareness, OpenAI client failure paths (timeout/429/500/invalid JSON/schema
  mismatch) with a stubbed HTTP client, service flow (issue/group targets,
  consistency, 404/409, provider failures, metadata stamping, no secrets),
  and API surface (401/404/409/422/502/503, no "best strategy" wording).
  **No real LLM key required.**
- Frontend (10 new tests — full suite 90): generate button, loading state,
  successful rendering of candidate cards, error + retry, safe rendering,
  no "best/recommended" wording.

## 14. Limitations

- Strategies are generated **on demand and not persisted** (by design — the
  persistence/versioning design belongs to later evaluation/ranking modules).
- The mock provider is for tests/demos only; real-strategy quality depends on
  the configured model and prompt version.
- Group-level generation is deterministic-grouping based; no embeddings or ML
  clustering.
- Single-target generation (one issue or one group per request).

## 15. Future evaluation/ranking

The `CandidateStrategy` fields (impact, effort, maintainability, WCAG
alignment, risks, confidence) and the traceability metadata are exactly the
input the Module 5 evaluation and Module 6 ranking modules will consume.
No further backend changes are required before starting them.
