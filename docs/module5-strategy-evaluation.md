# Module 5 — Strategy Evaluation

Status: **COMPLETE and verified** (live E2E with the deterministic mock
evaluator; real LLM requires credentials — see [Reproducibility](#14-reproducibility)).

## 1. Objective

Module 4 generates 2–5 **candidate** remediation strategies per accessibility
finding. Module 5 evaluates **every candidate independently** across seven
bounded dimensions, producing structured, traceable evaluation evidence for a
later ranking module (Module 6).

The pipeline becomes:

```
ContextDocument
      ↓
Candidate Strategies        (Module 4)
      ↓
Module 5 — Strategy Evaluation
      ↓
Evaluation of EACH strategy
      ↓
7-dimensional scores + strengths/weaknesses/rationale/evidence
      ↓
Module 6 — Strategy Ranking   (NOT implemented here)
```

## 2. Research motivation

The research contribution is a *context-aware multi-strategy framework*. The
evaluator must answer not only

> "Is this generally a valid accessibility technique?"

but

> "Is this technique appropriate for **THIS** issue, **THIS** element and
> **THIS** context?"

so the evaluator consumes the full `ContextDocument` (rule, WCAG information,
DOM/HTML evidence, affected element, page context) plus the candidate strategy
itself. The evaluation is therefore **context-aware**, not a generic review.

Module 5 deliberately produces multidimensional evidence and **nothing else**:
no total score, no rank, no winner. Combining dimensions and selecting the
contextually most suitable strategy is Module 6's job, and merging those
responsibilities would damage the research separation.

## 3. Architecture

```
POST /api/v1/scans/{scan_id}/evaluations
  → StrategyEvaluationService            (target resolution, strategy validation, stamping)
      → ContextBuilder (ContextBuilderService)   (ownership 404-safe, COMPLETED-only 409)
      → StrategyEvaluationProvider (protocol — never a concrete LLM class)
          ├── OpenAIEvaluationProvider    (any OpenAI-compatible /chat/completions endpoint)
          └── MockEvaluationProvider      (deterministic, clearly labeled, tests/demos)
      → prompts.py                        (versioned: trusted system vs. <untrusted> data)
      → EvaluationDraft → StrategyEvaluation (traceability stamped by the service)
```

The API never instantiates an evaluator class. New evaluators implement the
`StrategyEvaluationProvider` protocol and register in
`app/evaluations/providers/create_provider` — no service or API changes.

## 4. Evaluation criteria

Every candidate strategy is evaluated independently on **seven** dimensions:

1. **Accessibility Impact** — how much the strategy improves accessibility
   for the affected element/issue.
2. **WCAG / Standards Compliance** — how well it satisfies the WCAG criteria
   reported by the scanner (never invented criteria).
3. **Contextual Suitability** — how appropriate the technique is for *this*
   specific issue, element and DOM context (the core research dimension).
4. **Implementation Effort** — how much work the fix requires.
5. **Maintainability** — how easy the fix is to keep correct over time.
6. **Compatibility** — browser/assistive-technology support and regression
   risk.
7. **Risk** — the likelihood/severity of negative side effects.

## 5. Score semantics

Each score is an **integer 0–10**:

| Criterion | 10 means | 0 means |
|---|---|---|
| Accessibility Impact | excellent | extremely poor |
| Standards Compliance | excellent | extremely poor |
| Contextual Suitability | excellent | extremely poor |
| Implementation Effort | **very easy / very low effort** | extremely difficult / very high effort |
| Maintainability | excellent | extremely poor |
| Compatibility | excellent | extremely poor |
| Risk | **very low risk** | very high risk |

The effort and risk semantics are **inverted relative to the positive
criteria** and are documented both in the domain model docstring and in the
prompt. The model never inverts them accidentally — the fields are distinct
and bounded.

## 6. CandidateStrategy → StrategyEvaluation flow

Because Module 4 generates strategies **on demand** (they are never
persisted), the evaluation request carries the full candidate strategies plus
their ids:

```json
{
  "issue_id": "...",
  "group_id": "...",
  "strategy_ids": ["..."],
  "strategies": [ { CandidateStrategy }, ... ]
}
```

The service:

1. Builds the deterministic `ContextDocument` for the scan (JWT ownership;
   missing/foreign scan → 404; non-completed scan → 409).
2. Resolves the target issue/group against the context (404 if unknown).
3. **Re-validates every supplied strategy** against the deterministic
   context — issue membership, context version, evidence reference, group
   consistency — so client-supplied ids are never trusted blindly (422 on
   mismatch).
4. For each strategy: builds the versioned evaluation prompt (trusted system
   instructions vs. `<untrusted>` webpage/strategy data) and calls the
   provider.
5. Validates the provider's `EvaluationDraft` (schema + all seven bounded
   scores + matching `strategy_id`).
6. Stamps research traceability into a final `StrategyEvaluation` and returns
   an `EvaluationBatch` — one evaluation per strategy, **never a ranking**.

## 7. Provider abstraction

```python
class StrategyEvaluationProvider(Protocol):
    name: str
    async def evaluate(self, request: StrategyEvaluationRequest) -> EvaluationDraft: ...
```

The `StrategyEvaluationRequest` is self-contained (versioned prompts +
strategy + resolved target evidence + model settings), so providers stay
stateless. The service depends on the protocol only.

## 8. Prompt architecture

`EVALUATION_PROMPT_VERSION = "1.0"`. The system prompt (trusted, controlled)
is kept separate from the user prompt; inside the user prompt every piece of
scanner/webpage/strategy-derived data is wrapped in explicit
`<untrusted>…</untrusted>` markers, and the model is told that anything inside
them is *data*, never instructions. The prompt instructs the evaluator to:

- evaluate the **actual supplied strategy** (not rewrite it),
- use the supplied context and never invent website/WCAG facts,
- prefer native semantic HTML; justify ARIA only in context,
- produce exactly seven bounded scores with the documented semantics,
- never rank, never select a winner, never call anything best/recommended,
- return strict JSON.

## 9. Structured output

The provider must return a single JSON object matching `EvaluationDraft`:
seven integer scores (0–10), `strengths`, `weaknesses`, `rationale`,
`assumptions`, `uncertainties`, `evidence_references`, plus a `strategy_id`
that must match the supplied strategy. The service validates everything and
rejects invalid output with a sanitized `evaluation_output_invalid` (502) —
raw provider responses are never echoed.

## 10. Security

- All webpage/scanner/strategy content is treated as **untrusted**; prompt
  injection inside evidence cannot override the trusted system instructions.
- No `user_id` is ever accepted from the client; identity comes from the JWT.
- Strategies supplied by the client are re-validated against the
  deterministic context before evaluation.
- Provider failures return sanitized messages (no raw bodies, no internal
  URLs, no credentials). API keys live only in the `Authorization` header.
- The frontend renders evaluations as plain text — no strategy/HTML content
  is ever executed.

## 11. Error handling

All errors use the project's uniform `{code, message}` envelope:

| Case | HTTP | code |
|---|---|---|
| Unauthenticated | 401 | (auth) |
| Missing/foreign scan | 404 | `scan_not_found` |
| Unknown issue/group | 404 | `evaluation_target_not_found` |
| Strategy/context mismatch | 422 | `evaluation_strategy_invalid` |
| Request validation | 422 | (pydantic) |
| Non-completed scan | 409 | `context_unavailable` |
| Missing LLM configuration | 503 | `evaluation_configuration_error` |
| Provider timeout/rate limit/network | 502 | `evaluation_provider_error` |
| Invalid provider output | 502 | `evaluation_output_invalid` |

## 12. Testing

Backend (79 new tests, all deterministic, no network/Supabase/LLM key):

- **Models** — score bounds 0–10 for all seven dimensions, effort/risk
  semantics as distinct fields, version default, no-total/no-rank fields,
  request schema (target requirement, `strategy_ids`/`strategies`
  consistency), list sanitization.
- **Prompts** — version, trusted/untrusted separation, context + strategy
  injection, output contract, determinism, no-ranking wording.
- **Providers** — factory dispatch, mock determinism, per-type score
  semantics, context references, ARIA contextual adjustment, OpenAI
  sanitized failure paths (timeout, rate limit, upstream error, invalid
  JSON/shape) via a stubbed HTTP client.
- **Service** — independent per-strategy evaluations, batch metadata,
  issue/group targets, ownership 404s, 409 non-completed, strategy/context
  mismatch 422s, provider failures, wrong-strategy rejection, determinism,
  no-secrets/no-total/no-rank.
- **API** — 401/200/404/409/422/503/502 paths and payload guarantees.

Frontend (8 new tests): evaluate button, loading state, all seven score
categories, multiple independent evaluations, error + retry, safe rendering,
no best/winner/rank wording.

All Module 0–4 tests remain green (389 backend / 98 frontend).

## 13. Limitations

- Evaluations are generated **on demand** and not persisted (by design —
  persistence/versioning is deferred to the ranking/research modules).
- The mock evaluator is a deterministic demonstration only; real evaluation
  quality depends on the configured LLM.
- The evaluator cannot run a screen reader; automated evaluation cannot fully
  verify real assistive-technology behavior (stated as an uncertainty in
  every evaluation).
- Single-target evaluation (one issue or one group per request).

## 14. Reproducibility

Real LLM evaluation is probabilistic; the system does **not** claim
deterministic LLM output. Instead every evaluation captures safe traceability:

- `evaluation_id` (deterministic: `eval-{strategy_id}`)
- scan / issue / group ids, `context_version`, `evaluation_version`
- `prompt_version`, `evaluator_provider`, `evaluator_model`, `evaluated_at`
- temperature/model settings come from `LLM_TEMPERATURE` / `LLM_MODEL`

The **mock provider is fully deterministic**: identical inputs produce
byte-identical evaluation content. The `ContextDocument` itself remains
deterministic. No credentials, tokens, or user identity ever appear in
evaluation metadata.

## 15. Why ranking is intentionally excluded

Module 5 produces multidimensional evidence so that Module 6 can rank
strategies according to the *research question* — contextual suitability
across accessibility impact, effort, maintainability, standards compliance,
compatibility and risk. If Module 5 collapsed the seven dimensions into one
number or picked a winner, the ranking research (weighting, trade-offs,
human assessment) would be irreversibly baked into a single heuristic.

## 16. Future Module 6 ranking

Module 6 will consume `EvaluationBatch` (one `StrategyEvaluation` per
candidate) plus the traceability metadata to combine the seven dimensions
into a contextual ranking. The design keeps each dimension separate so the
ranking method itself can be researched and evaluated.

---

**Module 5 evaluates candidate strategies independently.**

It does **NOT**:

- rank strategies
- select a winner
- recommend a strategy
- calculate a final weighted score
- modify code
- apply remediation
