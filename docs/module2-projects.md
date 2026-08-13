# Module 2 — Project Management & Database Foundation

> Module 2 ships the first **real persistence-backed feature**: projects owned
> by an authenticated user, backed by a Supabase PostgreSQL table with strict
> Row Level Security. It is the foundation for Modules 3+ (scans → issues →
> context → remediation strategies).
>
> The module was delivered as a full-stack batch: migration + RLS, backend
> CRUD API (`route → schema → service → repository`), and a React UI (list,
> create, details, edit, delete). **The SQL migration is not applied
> automatically** — see §7 for how to run it.

## 1. Data model

```
User (auth.users)
  ↓ 1:N  (projects.user_id → auth.users.id, ON DELETE CASCADE)
Project
  ↓ 1:N  (future: scans.project_id)
Scans → Accessibility Issues → Context → Remediation Strategies
```

`public.projects` (see `supabase/migrations/20260813000001_create_projects.sql`):

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `user_id` | `uuid` | NOT NULL, FK → `auth.users(id)` ON DELETE CASCADE |
| `name` | `text` | NOT NULL, `char_length(trim(name)) BETWEEN 1 AND 100` |
| `description` | `text` | NOT NULL default `''`, `char_length ≤ 2000` |
| `website_url` | `text` | NOT NULL, `char_length ≤ 2048` |
| `status` | `text` | NOT NULL default `'NOT_SCANNED'`, CHECK in `('NOT_SCANNED','SCANNING','SCANNED','FAILED')` |
| `created_at` | `timestamptz` | NOT NULL default `now()` |
| `updated_at` | `timestamptz` | NOT NULL default `now()`, auto-updated by trigger |

Index: `projects_user_id_created_at_idx (user_id, created_at desc)` — supports
the common "my projects, newest first" query.

The status CHECK constraint keeps the lifecycle controlled
(`NOT_SCANNED → SCANNING → SCANNED | FAILED`); the backend enum
`ProjectStatus` mirrors it, and Pydantic rejects unknown values with 422.

## 2. Row Level Security

The table has RLS **enabled** and four policies, all keyed on
`auth.uid()` — a user can only ever see/touch their own rows:

| Policy | Operation | Condition |
| --- | --- | --- |
| Users can create their own projects | INSERT | `with check (auth.uid() = user_id)` |
| Users can view their own projects | SELECT | `using (auth.uid() = user_id)` |
| Users can update their own projects | UPDATE | `using` + `with check (auth.uid() = user_id)` |
| Users can delete their own projects | DELETE | `using (auth.uid() = user_id)` |

RLS protects **direct client access**. The backend talks to PostgREST with the
**service-role key**, which bypasses RLS — so ownership is additionally
enforced in the repository layer (§4), giving defense in depth:

- Database: RLS blocks any direct/anon/client request to another user's rows.
- Repository: every PostgREST query filters `user_id=eq.<uid>` (also for
  service-role calls).
- Service + routes: `user_id` is always derived from the authenticated JWT,
  never from the request body; a missing **or** not-owned project surfaces as
  the same 404 (`project_not_found`) so responses never leak whether another
  user's project exists (IDOR-safe).

## 3. API surface

All endpoints require a valid bearer token (`get_current_user` → 401
otherwise) and are mounted at `/api/v1`:

| Method | Path | Body | Success |
| --- | --- | --- | --- |
| POST | `/api/v1/projects` | `name`, `description?`, `website_url` | 201 |
| GET | `/api/v1/projects` | — | 200 (array, newest first) |
| GET | `/api/v1/projects/{id}` | — | 200 |
| PATCH | `/api/v1/projects/{id}` | any of `name` / `description` / `website_url` / `status` (≥1 required) | 200 |
| DELETE | `/api/v1/projects/{id}` | — | 204 |

The response never includes `user_id`. Errors use the uniform
`{code, message}` envelope (same as auth):

| Code | Status | Meaning |
| --- | --- | --- |
| `project_not_found` | 404 | Missing **or** not owned by the caller |
| `project_configuration_error` | 503 | Supabase selected but `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` missing |
| `project_error` | 500 | Unexpected PostgREST failure (message sanitized) |

`website_url` validation + normalization (422 on failure): must be `http(s)`,
include a host, contain no whitespace, ≤ 2048 chars; stored normalized
(lowercased scheme/host, default port dropped, root trailing slash stripped,
fragment removed).

## 4. Backend architecture

Follows the existing layered convention — route → schema → service →
repository — plus the auth dependency for identity:

```
routes/projects.py        # thin HTTP layer; derives ownership from the JWT
  → dependencies/projects.py   # DI seam: get_project_service
  → services.py (ProjectManagementService)
  → interfaces.py (ProjectRepository protocol)      ← persistence boundary
  → repositories/projects.py (SupabaseProjectRepository, PostgREST)
```

| File | Role |
| --- | --- |
| `app/projects/models.py` | Domain contracts: `Project`, `ProjectCreateInput`, `ProjectCreate`, `ProjectUpdate`, `ProjectStatus` enum |
| `app/projects/interfaces.py` | `ProjectRepository` protocol — every method takes `user_id`; implementations MUST scope queries to it |
| `app/projects/exceptions.py` | `ProjectError` hierarchy with `status_code` + `code` (mirrors auth exceptions) |
| `app/projects/services.py` | `ProjectManagementService` — ownership business rules, 404 mapping |
| `app/repositories/projects.py` | `SupabaseProjectRepository` — PostgREST CRUD with service-role key, ownership filters, row mapping, sanitized errors |
| `app/schemas/projects.py` | Request/response Pydantic models + URL normalization |
| `app/api/routes/projects.py` | The five endpoints |
| `app/dependencies/projects.py` | `get_project_repository` / `get_project_service` DI |
| `app/api/errors.py` | `ProjectError` handler registered next to `AuthError` (no change to the auth envelope) |

## 5. Frontend

React Query owns data fetching; the project UI lives under `/projects`:

| File | Role |
| --- | --- |
| `src/services/projectService.ts` | The only module that calls the projects API (via `@/lib/api`, which attaches the bearer token and normalizes errors); maps `snake_case` rows → `camelCase` |
| `src/hooks/useProjects.ts` | `useProjects` / `useProject` / `useCreateProject` / `useUpdateProject` / `useDeleteProject` with cache invalidation |
| `src/lib/projectValidation.ts` | Client-side form validation mirroring the backend rules |
| `src/pages/ProjectsPage.tsx` | List + empty/loading/error states + create/delete entry points |
| `src/pages/ProjectDetailsPage.tsx` | Detail view: status badge, edit form, delete confirmation dialog |
| `src/components/projects/` | `ProjectCard`, `CreateProjectModal` |

The dashboard header links to `/projects`; the page is protected by
`ProtectedRoute` (from Module 1, unchanged).

## 6. Testing

| Suite | Files | Coverage |
| --- | --- | --- |
| Backend (pytest) | `test_projects.py`, `test_project_repository.py` | Full CRUD over an in-memory repository implementing the contract (ownership/IDOR end-to-end without network): auth required (401), create (ownership from JWT, not body; URL normalization; invalid URL/name/description → 422), list filtered per user, get/update/delete of own vs. another user's project (404, row untouched), malformed id → 422, status enum validation, service-level scoping. Repository tests use a fake HTTP transport (same convention as auth): PostgREST URLs/headers/params/body, ownership filters in every query, empty/no-op update fallback, config-required-before-network, sanitized error mapping (no secret leakage). |
| Frontend (vitest) | `useProjects.test.tsx`, `ProjectsPage.test.tsx`, `projectService.test.ts` | Hooks fetch + mutate + invalidate; page renders list/loading/empty/error states, create via modal, client-side validation, delete confirmation, API error surfacing; service maps rows. |

Backend tests replace `get_current_user` and `get_project_service` via
dependency overrides; no network and no real credentials are ever used.

## 7. Migration handling

Migrations are **not run automatically** — this repo has no migration runner
yet. The SQL file lives in `supabase/migrations/`. To apply it:

1. Open the Supabase Dashboard → SQL Editor.
2. Paste the contents of `supabase/migrations/20260813000001_create_projects.sql`.
3. Run it (idempotent: `drop trigger if exists`, extension guard).

The file enables RLS itself and ships the ownership policies, so no extra
configuration is needed. Until it is applied, the projects API answers
`project_configuration_error` (503) — the same degrade-gracefully pattern as
auth.

## 8. Environment

Reuses the existing variables — no new ones:

| Variable | Where | Used for |
| --- | --- | --- |
| `SUPABASE_URL` | `backend/.env` | PostgREST base URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/.env` | Service-role key (bypasses RLS; ownership enforced in queries) |

## 9. Security notes

- Strict RLS keyed on `auth.uid()`; never weakened for development.
- IDOR-safe: ownership derived from the JWT, repository queries always filter
  `user_id`, and missing/foreign resources return an identical 404.
- `user_id` cannot be set from the request body (it is not part of the
  request schemas; a supplied value is ignored).
- Service-role key lives only in `backend/.env` (gitignored), never in the
  browser; errors are sanitized so credentials never leak into messages.
- URL input is validated and normalized server-side; client validation is
  purely UX.

## 10. Future work (Modules 3+)

- `scans` table referencing `projects.id` (the schema is ready for it).
- A migration runner / `supabase db` workflow to apply migrations from CI.
- Issue/context/strategy tables and the decision pipeline.
