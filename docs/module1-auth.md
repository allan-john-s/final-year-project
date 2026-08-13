# Module 1 — Authentication (Batch 1: infrastructure + Batch 2: Supabase + finalization)

> **Batch 1** shipped the provider-agnostic authentication infrastructure —
> interfaces, DI, guards, pages — with every endpoint answering **501**.
> **Batch 2** replaced the placeholder with a real **Supabase Auth** provider on
> both sides of the stack: session persistence, automatic token refresh, a
> bearer dependency, and `/api/v1/auth/me`.
>
> **Batch 2 finalization** upgraded token verification from the legacy
> `SUPABASE_JWT_SECRET` / HS256 shared-secret approach to **modern asymmetric
> verification against Supabase's JWKS endpoint** (RS256/ES256), with
> `iss` / `aud` / `exp` / `sub` validation and automatic key-rotation recovery.
>
> The provider abstraction is unchanged. With no credentials in the
> environment the app still runs on the placeholder (operations return 501),
> so development and tests never require a Supabase project.

## 1. Architecture

Authentication is built around a **provider abstraction** on both sides of the
stack. The application never talks to an identity provider directly — it talks
to an interface, and a *provider* implements that interface.

```
                        ┌─────────────────────────────┐
                        │        AuthProvider         │
                        │  (contract / Protocol)      │
                        └─────────────────────────────┘
                                   ▲
              ┌────────────────────┼────────────────────┐
              │                    │                    │
   ┌──────────┴──────────┐ ┌───────┴────────┐ ┌─────────┴─────────┐
   │  SupabaseProvider   │ │ FirebaseProvider│ │  Auth0Provider   │
   │  (Batch 2)          │ │   (future)      │ │   (future)       │
   └─────────────────────┘ └────────────────┘ └───────────────────┘
```

Swapping providers requires no code changes anywhere else — only the registry
entry (backend) / factory (frontend) changes.

### Backend flow

```
route handler (app/api/routes/auth.py)
   → Depends(get_auth_service)          # DI seam
   → AuthService protocol                # app/auth/interfaces.py
   → provider from registry              # app/auth/providers/registry.py
       SupabaseAuthProvider when SUPABASE_URL is set, else placeholder (501)
   → AuthError subclasses → JSON handler # app/api/errors.py
```

Protected routes (`GET /api/v1/auth/me`) use a second dependency:

```
AuthenticationMiddleware   # non-blocking; caches verified user on request.state
   → Depends(get_current_user)          # bearer token → AuthUser (401 on failure)
       → SupabaseAuthProvider.verify_access_token
           → SupabaseJwtVerifier (JWKS)  # asymmetric, no shared secret
```

### Frontend flow

```
pages → useAuth() hook → AuthContext → AuthService interface → createAuthService()
                              ▲
ProtectedRoute / GuestRoute   │
(route guards read status)    └── SupabaseAuthService when VITE_SUPABASE_* set,
                                   else placeholder (NotImplementedAuthService)
```

## 2. Provider abstraction

### Backend (`backend/app/auth/`)

| File | Role |
| --- | --- |
| `interfaces.py` | `AuthUser`, `AuthResult`, input models, and the `AuthService` `Protocol` (incl. `verify_access_token`) |
| `exceptions.py` | `AuthError` hierarchy; each carries `status_code` + machine-readable `code` (401/403/404/409/501/503) |
| `jwt.py` | `TokenPayload`, `TokenPair`, token protocols (models only — no shared-secret logic) |
| `jwks.py` | `SupabaseJwtVerifier` — JWKS-backed asymmetric verification (PyJWT `PyJWKClient`): fetch + TTL cache, `kid` matching, rotation refetch, `iss`/`aud`/`exp`/`sub` checks |
| `providers/base.py` | `AuthProvider` marker protocol (`AuthService` + `name`) |
| `providers/supabase.py` | `SupabaseAuthProvider` — JWKS token verification + GoTrue REST via service-role key |
| `providers/not_implemented.py` | `NotImplementedAuthProvider` — every call raises `AuthNotConfiguredError` (→ 501) |
| `providers/registry.py` | `get_auth_provider()` — selects Supabase when `SUPABASE_URL` is set |

### Frontend (`frontend/src/services/auth/`)

| File | Role |
| --- | --- |
| `types.ts` | `AuthUser`, input models, `AuthResult`, the `AuthService` interface + optional session-lifecycle hooks |
| `errors.ts` | `AuthError`, `AuthNotImplementedError`, `AuthConfigurationError`, `AuthEmailVerificationRequiredError` |
| `supabase.ts` | `SupabaseAuthService` — all identity work delegated to supabase-js |
| `notImplemented.ts` | `NotImplementedAuthService` — `getCurrentUser()` resolves `null`; everything else raises |
| `index.ts` | Barrel + `createAuthService()` factory — the single seam for swapping providers |
| `../lib/supabase.ts` | Lazy Supabase client (singleton) built from `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` |

Consumers (`AuthContext`, `useAuth`, pages, route guards) import from
`@/services/auth` and only depend on the `AuthService` interface.

## 3. Folder responsibilities

```
frontend/src/
  contexts/AuthContext.tsx          # session state, restore, auth-state listener
  hooks/useAuth.ts                  # context consumer hook
  services/auth/                    # provider abstraction + Supabase implementation
  lib/supabase.ts                   # Supabase client bootstrap (lazy singleton)
  components/auth/
    AuthShell PasswordInput LoadingScreen FormError
    ProtectedRoute GuestRoute        # unchanged since Batch 1
  pages/auth/ Login Register ForgotPassword ResetPassword EmailVerification
  lib/validation.ts                 # shared form validation

backend/app/
  auth/                             # domain: interfaces, exceptions, jwt, jwks, providers
  dependencies/auth.py              # get_auth_service + get_current_user (bearer)
  api/middleware.py                 # AuthenticationMiddleware (non-blocking cache)
  api/routes/auth.py                # /api/v1/auth/* incl. protected /me
  api/errors.py                     # AuthError → JSON envelope
  core/config.py                    # Settings incl. SUPABASE_* (safe defaults)
  tests/ test_auth.py test_jwt.py test_supabase_provider.py conftest.py
```

## 4. API surface

| Method | Path | Body | Success | Auth |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/signup` | email, password, display_name? | 201 | — |
| POST | `/api/v1/auth/login` | email, password | 200 (tokens) | — |
| POST | `/api/v1/auth/logout` | — | 204 | — |
| GET | `/api/v1/auth/me` | — | 200 | Bearer (401 without) |
| POST | `/api/v1/auth/password/forgot` | email | 202 | — |
| POST | `/api/v1/auth/password/reset` | token, new_password | 204 | — |
| POST | `/api/v1/auth/email/verify` | token | 204 | — |

Error envelope (all `AuthError`s):

```json
{ "code": "invalid_token", "message": "The access token is invalid." }
```

| Code | Status | Meaning |
| --- | --- | --- |
| `auth_not_configured` | 501 | Placeholder provider (no credentials) |
| `auth_configuration_error` | 503 | Provider selected but a credential missing / JWKS unreachable |
| `authentication_required` | 401 | No/invalid bearer token |
| `invalid_token` | 401 | Malformed/bad-signature/wrong-issuer/wrong-audience token |
| `token_expired` | 401 | Token past `exp` |
| `invalid_credentials` | 401 | Wrong email/password |
| `email_already_registered` | 409 | Duplicate sign-up email |
| `user_not_found` | 404 | Unknown user |

## 5. Authentication flow (end to end)

1. **Sign up** — frontend `signUp()` → supabase-js `signUp`. If email
   confirmation is required (no session returned) the pending email is stored
   in `sessionStorage` and the page shows *"check your email"*; otherwise the
   user is signed straight in.
2. **Email verification** — the `?token=` page (or manual entry) calls
   `verifyEmail()` → `verifyOtp({ type: 'signup' })` using the remembered
   email; the pending email is cleared on success.
3. **Sign in** — `signIn()` → supabase-js `signInWithPassword`; the session is
   persisted to Supabase's localStorage store.
4. **Protected pages** — `ProtectedRoute` renders only when the context status
   is `authenticated`; the guard reads the status, never the provider.
5. **Session restore** — on boot, `AuthContext` calls `restoreSession()`
   (`getSession()` — localStorage, no network) and subscribes to
   `onAuthStateChange` for every later change (sign in/out, refresh,
   cross-tab, confirmation).
6. **API calls** — the backend's `get_current_user` dependency verifies the
   bearer JWT via the JWKS endpoint (`SupabaseJwtVerifier`) and returns the
   user; `/me` exercises exactly this path.
7. **Sign out** — `signOut()` → supabase-js `signOut` (revokes the refresh
   token); the auth-state listener flips the context to unauthenticated and
   `ProtectedRoute` redirects to `/login`.

## 6. JWT verification architecture (modern, asymmetric)

Supabase's **JWT Signing Keys** system signs access tokens with private keys
and exposes the **public** signing keys at a JWKS endpoint — no shared secret
is ever needed by this backend.

```
GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json     # public keys (RS256/ES256)
issuer: {SUPABASE_URL}/auth/v1                        # expected iss claim
audience: "authenticated"                             # expected aud claim
```

`SupabaseJwtVerifier` (PyJWT `PyJWKClient`):

1. Reads the token's `kid` header and fetches/matches the signing key from the
   cached JWKS document (TTL cache, default 300 s).
2. Verifies the **signature** first — claims are never trusted before this.
3. Enforces `iss` = `{SUPABASE_URL}/auth/v1`, `aud` = `authenticated`,
   `exp` validity, and the presence of `sub`/`exp`/`iat`.
4. On an unknown `kid` (key rotation) the document is **refetched once**
   automatically, so rotation requires no restart or code change.
5. Failures map onto the exception hierarchy: `token_expired` / `invalid_token`
   (401) and `auth_configuration_error` (503) when the JWKS endpoint is
   unreachable.

The verifier is cached per project URL and shared across requests. It accepts
an injectable client/fetcher so unit tests serve a canned JWKS document
in-memory — no network, no real keys.

Token lifecycle: Supabase issues access + refresh tokens; the frontend
refreshes automatically via supabase-js; this backend never issues tokens and
only *verifies* access tokens with public keys.

## 7. Session lifecycle (frontend)

- **Persistence** — supabase-js `persistSession: true` keeps the session in
  localStorage (never our code).
- **Auto refresh** — supabase-js `autoRefreshToken: true` refreshes the access
  token shortly before expiry; `TOKEN_REFRESHED` events reach the context via
  `onAuthStateChange`, so the UI stays in sync.
- **Recovery** — `restoreSession()` on mount rehydrates from localStorage
  before the first render settles (context starts in `loading`).
- **Cross-tab / logout** — auth events (`SIGNED_OUT`, `SIGNED_IN`, …) update
  the context and therefore `ProtectedRoute` / `GuestRoute` automatically.
- **Passwords** are never stored locally or by the backend; only Supabase
  holds them.

## 8. Environment variables

| Variable | Where | Required | Found in Supabase dashboard |
| --- | --- | --- | --- |
| `VITE_SUPABASE_URL` | `frontend/.env` | yes (frontend auth) | Project Settings → API → Project URL |
| `VITE_SUPABASE_ANON_KEY` | `frontend/.env` | yes (frontend auth) | Project Settings → API → **Publishable key** (`sb_publishable_...`, the new anon key — public by design) |
| `VITE_API_URL` | `frontend/.env` | yes (API client) | — |
| `SUPABASE_URL` | `backend/.env` | yes (backend) | Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/.env` | yes (backend admin/flow ops) | Project Settings → API → **Secret key** (`sb_secret_...`, service_role) |

> **Publishable vs Secret key** — the frontend uses only the **publishable**
> key (safe in the browser bundle). The backend uses the **secret** key for
> admin/flow operations only; it must never be exposed to the frontend and is
> not required for JWT verification (JWKS is public-key based).

Copy values from `frontend/.env.example` / `backend/.env.example` into local
`.env` files. Nothing is hardcoded; without the variables the app degrades to
the placeholder provider (auth endpoints answer 501/503). The legacy
`SUPABASE_JWT_SECRET` is **no longer used** and must not be configured.

## 9. Security notes

- Supabase Auth only — no custom credential handling anywhere.
- JWT bearer authentication on the backend; tokens verified with **public
  keys** via JWKS — signature is checked before any claim is trusted, and
  `iss` / `aud` / `exp` / `sub` are all enforced.
- Automatic session refresh client-side; expiry handled on both sides.
- No passwords stored locally; the backend uses the service-role (secret) key
  only for admin/flow endpoints and never sees a user password beyond the
  sign-in request.
- Secret key must never ship to the browser — it lives only in `backend/.env`
  (gitignored). The publishable key is the only Supabase credential exposed to
  the frontend.
- Errors return the uniform envelope with no stack traces, JWT contents, or
  credentials.
- Key rotation is handled automatically (unknown `kid` → JWKS refetch).

## 10. Testing

| Suite | Files | Coverage |
| --- | --- | --- |
| Frontend (vitest) | `authService.test.ts`, `supabase.test.ts`, `ProtectedRoute.test.tsx`, `GuestRoute.test.tsx`, `lib/validation.test.ts` | service factory (Supabase vs placeholder), sign in/up, logout, session restore, token-refresh listener, reset/verify flows, guards, auth error handling |
| Backend (pytest) | `test_auth.py`, `test_jwt.py`, `test_supabase_provider.py` | 501 surface, 422 validation, exception mapping, provider selection, `/me` (valid/invalid/expired/missing/wrong-scheme/**wrong-issuer**/**wrong-audience**), JWKS unit tests (RS256 + ES256, rotation refetch, unreachable endpoint), provider REST mapping (fake transport) |

Backend tests mint throwaway RSA/EC keys and serve the JWKS in-memory — no
network and no real credentials (`conftest.py` also neutralizes any local
`.env`). Frontend tests run in `test` mode where `frontend/.env.test` shadows
the real `.env`, so no credentials leak into the suite.

Run: `npm test` (frontend), `pytest` in `backend/` (backend). CI runs backend
pytest + frontend lint/build.

## 11. Local development

1. `cp frontend/.env.example frontend/.env` and `cp backend/.env.example
   backend/.env`; fill in your Supabase URL + publishable key (frontend) and
   URL + secret key (backend).
2. Backend: `cd backend && .venv/bin/uvicorn app.main:app --reload`
   (tests: `.venv/bin/python -m pytest`).
3. Frontend: `cd frontend && npm run dev` (tests: `npm test`).
4. `POST /api/v1/auth/login` and `GET /api/v1/auth/me` exercise the full
   JWKS verification path; without credentials the API answers 501/503.

## 12. Future work (later batches)

- Database tables + migrations (user profiles beyond auth).
- Email templates / redirect URLs configuration for the Supabase project.
- Additional providers (Firebase, Auth0) — implement `AuthService`, register in
  `providers/registry.py` / `createAuthService()`, nothing else changes.
- Row-level security policies driven by `TokenPayload` claims.
