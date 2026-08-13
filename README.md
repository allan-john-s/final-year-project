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

> **Status: Modules 1–2 complete.** Module 1 shipped provider-agnostic authentication
> infrastructure plus a real **Supabase Auth** provider with **JWKS-based asymmetric JWT
> verification** (`iss`/`aud`/`exp`/`sub` checks, automatic key-rotation recovery),
> bearer-authenticated `/api/v1/auth/me`, session persistence, and auto token refresh — see
> `docs/module1-auth.md`. Module 2 added the first persistence-backed feature: **project
> management** (Supabase `projects` table + strict RLS, full CRUD API, React UI) as the
> foundation for scans/issues/remediation — see `docs/module2-projects.md`. No scanning or AI yet.

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
| 3      | URL validation + scanner service integration       | ⏳ Pending |
| 4+     | Context builder, strategy generation, evaluation, ranking, explanation, re-scan | ⏳ Pending |

## License

TBD — research project; discuss before publishing.
