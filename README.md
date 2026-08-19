# A Context-Aware Multi-Strategy Framework for AI-Assisted Web Accessibility Remediation

> Publication-ready final-year research project — a decision-support framework that helps developers
> choose the best remediation strategy for every detected accessibility issue.

## Research Contribution

Existing tools (axe-core, Lighthouse, WAVE, Pa11y) **detect** accessibility problems; none of them help
developers **decide how to fix them**. This project contributes a **Context-Aware Multi-Strategy Decision
Framework**:

```
Detect → Enrich Context → Generate Strategies → Evaluate → Rank → Recommend → Explain → Compare → Re-scan
```

Each step is an isolated, testable service so the decision pipeline itself is reproducible and defensible
in an IEEE / Springer / Scopus submission.

> **Status: Modules 1–7 complete.** Module 1 shipped provider-agnostic
> authentication infrastructure plus a real **Supabase Auth** provider with **JWKS-based
> asymmetric JWT verification** (`iss`/`aud`/`exp`/`sub` checks, automatic key-rotation
> recovery), bearer-authenticated `/api/v1/auth/me`, session persistence, and auto token
> refresh — see `docs/module1-auth.md`. Module 2 added **project management** (Supabase
> `projects` table + strict RLS, full CRUD API, React UI) — see `docs/module2-projects.md`.
> **Module 3A** shipped the **scanner architecture + database foundation** (scanner contract,
> normalized scan result models, `scans`/`accessibility_issues` tables with strict RLS,
> repository layer; migration manually applied) — see `docs/module3-scanner.md`. **Module 3B**
> shipped the **first real scanner engine** — axe-core via Playwright — plus the scan
> execution service, issue persistence, the scan API
> (`POST /projects/{id}/scan`, `GET /scans...`, `GET /scans/{id}/issues`, …) and a minimal
> React UI — see `docs/module3b-scanner-engine.md`. **Module 3C** added the **Context Builder**:
> a deterministic, versioned `ContextDocument` (project/scan/page/issue context, WCAG
> mapping, element evidence, issue groups) served by `GET /scans/{id}/context` with a React
> context view — see `docs/module3c-context-builder.md`. **Module 4** added the **multi-strategy
> generator**: a typed `CandidateStrategy` pipeline that turns a `ContextDocument` into 2–5
> validated, genuinely distinct remediation candidates via a provider abstraction
> (OpenAI-compatible + deterministic mock), with versioned prompts, structured-output
> validation, prompt-injection defenses and traceability metadata — served by
> `POST /scans/{id}/strategies` with candidate cards in the React context view — see
> `docs/module4-strategy-generation.md`. **Module 5** added the **strategy evaluator**: every
> candidate is evaluated independently across seven bounded 0–10 dimensions
> (accessibility impact, standards compliance, contextual suitability, implementation
> effort, maintainability, compatibility, risk) with strengths/weaknesses/rationale and
> full traceability — via a provider abstraction (OpenAI-compatible + deterministic
> mock), versioned evaluation prompts, prompt-injection defenses and strict structured
> output validation. No total score and no ranking by design — served by
> `POST /scans/{id}/evaluations` with per-candidate score bars in the React context view —
> see `docs/module5-strategy-evaluation.md`. **Module 6** added **context-aware strategy
> ranking**: transparent, deterministic weighted scoring across the seven evaluation
> dimensions with configurable baseline and context-aware modes, context factor detection
> from the ContextDocument, human-readable ranking explanations, and a baseline vs
> contextual comparison view — served by `POST /scans/{id}/ranking` with ranked strategy
> cards and comparison UI in the React context view — see `docs/module6-strategy-ranking.md`.
> Generation, evaluation, and ranking are all on demand; re-scanning and improvement measurement are next.

## Monorepo Layout

```
├── frontend/                 # React + Vite + TypeScript + TailwindCSS + shadcn/ui
├── backend/                  # FastAPI (Python 3.12) — API layer
│   └── app/
│       ├── api/              #   routers & route handlers
│       ├── core/             #   config, logging, app factory
│       ├── middleware/       #   HTTP middleware
│       ├── services/         #   application services (decision pipeline)
│       ├── repositories/     #   data access (repository pattern)
│       ├── schemas/          #   Pydantic v2 request/response schemas
│       ├── models/           #   domain models
│       ├── utils/            #   shared helpers
│       └── tests/            #   unit/integration tests
├── docs/                     # architecture, decisions (ADR), paper artifacts
├── scripts/                  # dev & CI helper scripts
└── .github/workflows/        # CI pipeline
```

## Tech Stack

| Layer     | Technology                                      |
| --------- | ----------------------------------------------- |
| Frontend  | React, Vite, TypeScript, TailwindCSS, shadcn/ui |
| Backend   | FastAPI, Python 3.12, Pydantic v2, Uvicorn      |
| Quality   | ESLint, Prettier, pytest, Docker, Git           |

## Quickstart

### Backend

```bash
cd backend
python3.12 -m venv .venv            # Python 3.12+
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload       # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

### Environment

Copy the example env files and fill in real values later:

```bash
cp frontend/.env.example frontend/.env
cp backend/.env.example backend/.env
```

## Module Plan

| Module | Scope                                              | Status     |
| ------ | -------------------------------------------------- | ---------- |
| 0      | Monorepo foundation (this batch)                   | ✅ Done    |
| 1      | Auth: infrastructure + Supabase provider + JWKS verification + `/me` | ✅ Done |
| 2      | Project management & database foundation (projects table + RLS + CRUD + UI) | ✅ Done |
| 3A     | Scanner architecture + database foundation (scanner contract, normalized models, `scans` + `accessibility_issues` tables + RLS, repository layer) | ✅ Done — migration applied |
| 3B     | Axe-core scanner engine (Playwright), scan execution service, issue persistence, scan API + minimal UI | ✅ Done |
| 3C     | Context Builder (deterministic ContextDocument, WCAG mapping, element evidence, issue groups, `GET /scans/{id}/context` + UI) | ✅ Done |
| 4      | Multi-strategy generation (CandidateStrategy pipeline, provider abstraction, versioned prompts, `POST /scans/{id}/strategies` + UI) | ✅ Done — mock provider live-verified; real LLM needs `LLM_API_KEY` |
| 5      | Strategy evaluation (independent 7-dimensional evaluation per candidate, provider abstraction, versioned evaluation prompts, `POST /scans/{id}/evaluations` + UI) | ✅ Done — mock evaluator live-verified; real LLM needs `LLM_API_KEY` |
| 6      | Context-aware strategy ranking (weighted scoring, baseline vs contextual, context factors, comparison, `POST /scans/{id}/ranking` + UI) | ✅ Done |
| 7      | Remediation (structured proposal generation, review-first workflow, status lifecycle, `POST /scans/{id}/remediation` + UI) | ✅ Done — mock provider; real LLM needs `LLM_API_KEY` |

## License

TBD — research project; discuss before publishing.
