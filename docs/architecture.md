# Architecture Overview

This document describes the monorepo architecture. It is a living document —
update it whenever the structure or conventions change.

## Layers

### Frontend (`frontend/`)

React single-page application. Data fetching is centralized in React Query
(tanstack-query); routing is handled by React Router. UI components come from
shadcn/ui (TailwindCSS + Radix primitives).

### Backend (`backend/`)

FastAPI application following a layered architecture:

```
api (routers) → services (business logic) → repositories (data access)
```

- **`api/`** — HTTP layer only. Route handlers validate input via Pydantic
  schemas, call a service, and return typed responses.
- **`services/`** — orchestration and domain logic (the decision pipeline in
  later modules).
- **`repositories/`** — persistence boundary; the only place that talks to
  storage. Swappable for tests.
- **`schemas/`** — Pydantic v2 models shared between API and services.
- **`core/`** — application settings, logging, app factory.

## Conventions

- Typed APIs everywhere: every request/response is a Pydantic schema.
- Services depend on abstractions (interfaces / protocols), never on concrete
  repositories directly — enables dependency injection in tests.
- SQL migrations live in `supabase/migrations` and are the only way the schema
  changes (applied manually in the Supabase dashboard until a migration runner
  is added).

## CI

See `.github/workflows/ci.yml` — the frontend must build and lint, the backend
must pass `pytest` on every push.
