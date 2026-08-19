# Module 3B — Axe-Core Scanner Engine & Scan Execution

> Module 3B ships the **first real scanner engine** (axe-core via Playwright),
> the **scan execution service**, the **issues persistence path**, the **scan
> API**, and the **minimal frontend integration** (start scan, poll, details,
> issue list). It builds directly on the Module 3A architecture — no schema or
> RLS changes were needed (the 3A migration was sufficient). **No AI, context
> builder, strategy generation, or remediation logic is implemented.**

```
Project
  ↓ owns
Scan (PENDING → RUNNING → COMPLETED / FAILED)
  ↓ owns
AccessibilityIssue (normalized axe violations)
```

## 1. Architecture

```
API routes (app/api/routes/scans.py)
  ↓  get_scan_service (DI)
ScanExecutionService (app/scans/services.py)
  ├── ProjectRepository     → ownership check before start
  ├── ScanRepository        → lifecycle CRUD (PostgREST, user-scoped)
  ├── AccessibilityIssueRepository → issue persistence (PostgREST, scan-scoped)
  └── scanner factory       → BaseScanner (never a concrete engine)
        ↓
AxeScanner (app/scanners/axe.py)  ← Playwright + vendored axe-core
        ↓
NormalizedScanResult (Module 3A contract)
```

- The API layer never instantiates a scanner — it asks the service, which
  resolves one through `SCANNER_REGISTRY` (`get_scanner(ScannerType.AXE)`).
- Adding Lighthouse/Pa11y/WAVE later = implement `BaseScanner` + register the
  class. No route, service, or schema changes.

## 2. Axe integration

`AxeScanner` (`app/scanners/axe.py`):

1. Validates the URL scheme (`http(s)://` → else `ScannerTargetError`).
2. Lazily imports **Playwright** (`_import_playwright`) so the app and the
   unit-test suite run without it installed.
3. Launches headless Chromium (channel overridable via `AXE_BROWSER_CHANNEL`,
   e.g. `chrome` to use an installed Chrome instead of bundled Chromium).
4. Navigates with a 30 s timeout (`wait_until="load"`); navigation timeout,
   no-response, and HTTP ≥ 400 are `ScannerTargetError`.
5. Injects the **vendored** axe-core script
   (`app/scanners/assets/axe.min.js`, pinned 4.10.2; override via
   `AXE_CORE_PATH`). No runtime CDN dependency.
6. Runs `axe.run(document, { resultTypes: ["violations", "passes", "incomplete"] })`.
7. Normalizes every violation node into `AccessibilityIssue` via the pure
   function `normalize_axe_result` (unit-tested without a browser).
8. Populates `ScanMetadata` (engine identity from `testEngine`, browser
   version, user agent, DOM element counts, `tested_elements` = unique
   targets axe reported) and `ScanTiming` (total + normalization ms).

### Normalization mapping

| Normalized field | axe source |
| --- | --- |
| `rule_id` | `violation.id` |
| `rule_name` / `help` | `violation.help` |
| `description` | `violation.description` |
| `help_url` | `violation.helpUrl` |
| `impact` | `node.impact` (fallback `violation.impact`), mapped to the controlled `Impact` enum; unknown → `MODERATE` (never fatal) |
| `wcag_level` | first WCAG tag in `violation.tags` (`wcag2a/aa/aaa`, `wcag21a/aa/aaa`, `wcag22a/aa/aaa`) |
| `tags` | `violation.tags` (non-empty strings) |
| `element_selector` / `dom_path` | `node.target` joined with ` > ` |
| `html_snippet` | `node.html` |
| `failure_summary` | `node.failureSummary` |
| `xpath` / `css_path` | left empty (axe doesn't report them — see Limitations) |

Every field is defensively truncated to its model/database limit so a
malformed or hostile page cannot crash normalization.

### Accessibility score

`calculate_accessibility_score(issues)` (in `app/scanners/models.py`):
deterministic weighted penalty, clamped to [0, 100] — 100 with no findings,
−10 per critical, −5 per serious, −2 per moderate, −1 per minor. Explicitly
**not** a machine-learning score; stable and explainable for the research
paper.

## 3. Scan lifecycle

Enforced at the domain layer (`assert_valid_transition` in
`app/scans/models.py`) and called by the service on every status change:

```
PENDING ──start_scan──▶ RUNNING ──execute_scan──▶ COMPLETED
                             │
                             └── any failure ──▶ FAILED
```

Illegal moves (e.g. PENDING → COMPLETED, re-running a completed scan) raise
`InvalidScanTransitionError` (409 `invalid_scan_transition`). Status values
are additionally constrained by the DB CHECK constraint.

Execution flow:

1. `POST /projects/{id}/scan` → service verifies the project is owned (404
   otherwise) and the scanner type is registered (503 otherwise), creates the
   scan `PENDING`, transitions to `RUNNING` (`started_at`), and schedules
   `run_scan` as a FastAPI background task. Returns the RUNNING scan (202).
2. `run_scan` → `execute_scan`: requires RUNNING, selects the scanner via the
   factory, scans the project URL, persists all issues
   (`accessibility_issues`), then persists the completed scan
   (`COMPLETED`, `completed_at`, `duration_ms`, counts, `summary`,
   `accessibility_score`, full scanner metadata, `persistence_duration_ms`).
3. **Failure** → the scan is marked `FAILED` with a **sanitized** message in
   `summary.error` (whitespace-collapsed, truncated to 2000 chars — no stack
   traces) and `ScanExecutionError` (500 `scan_execution_failed`) is raised;
   the background wrapper logs and swallows it, so the row is the source of
   truth and a failed scan never crashes the request cycle.

Clients poll `GET /scans/{id}` (frontend auto-polls while PENDING/RUNNING)
until the terminal state.

## 4. API endpoints

All require a valid Bearer token; ownership always comes from the JWT
(never from the body).

| Method | Path | Status | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/projects/{project_id}/scan` | 202 | Start a scan (body: `{scanner_type?: "AXE"}`) |
| GET | `/api/v1/projects/{project_id}/scans` | 200 | Scans of an owned project (404 for others) |
| GET | `/api/v1/scans` | 200 | All of my scans, newest first |
| GET | `/api/v1/scans/{scan_id}` | 200 | Scan details (404 if missing/foreign) |
| GET | `/api/v1/scans/{scan_id}/issues` | 200 | Normalized issues (404 if missing/foreign) |
| DELETE | `/api/v1/scans/{scan_id}` | 204 | Delete my scan (cascades issues) |

Errors use the uniform `{code, message}` envelope via the existing exception
handlers.

## 5. Error handling

Scanner exceptions (`app/scanners/exceptions.py`):

- `ScannerConfigurationError` — Playwright missing, axe source missing,
  browser launch failure → the scan becomes FAILED with a sanitized message.
- `ScannerTargetError` — invalid/unreachable URL, navigation timeout, HTTP
  error status.
- `ScannerRuntimeError` — anything unexpected during execution.

None of these leak raw details to API clients: the service stores
`sanitize_failure_message(str(exc))` on the FAILED row and re-raises
`ScanExecutionError` with that sanitized text.

## 6. Security / RLS

- **No new migration** — the Module 3A schema (tables, indexes, cascades,
  RLS) was sufficient; nothing in 3B required a schema change.
- Repositories enforce ownership in the **query itself**: scans filter
  `user_id=eq.<uid>` on every operation; issues filter via
  `scans!inner(user_id)` on the owning scan — defense in depth below RLS.
- The service 404s for missing *and* foreign resources (`scan_not_found`,
  `project_not_found`) so responses never confirm another user's data.
- `user_id` is absent from every request/response schema; `project_id` only
  appears in the URL path.

## 7. Testing strategy

| Suite | Covers |
| --- | --- |
| `test_axe_scanner.py` | pure normalization (impact/WCAG mapping, malformed input), score calc, and the `scan()` driver with a **fake Playwright** (success, invalid URL, missing playwright, launch failure, navigation timeout, HTTP 503, malformed axe result, missing axe source) |
| `test_scan_service.py` | ownership, PENDING→RUNNING, COMPLETED persistence (counts/score/metadata/issues), failure→FAILED + sanitized message, transition validation, IDOR-safe reads/deletes |
| `test_scans_api.py` | 401s, POST scan → 202 RUNNING + background completion, 404s for foreign/missing, 422 for bad input, 503 for unregistered scanner, issues endpoint, delete |
| `test_issue_repository.py` | fake-transport PostgREST calls: bulk insert payload, ownership-filtered list, config guard, sanitized errors |
| `test_scanner_factory.py` | AXE registered, unregistered types raise, extension point |
| frontend | `scanService.test.ts` (mapping/payloads), `ScanDetailsPage.test.tsx` (completed/running/failed/error states) |

All unit tests are deterministic, network-free, and need no Supabase
credentials or installed browsers.

## 8. Live E2E (performed)

A controlled local page with deliberate violations (missing alt text, low
contrast, unlabeled input, missing `<html lang>`) was served locally and
scanned through the full stack. The run was verified end-to-end: user →
project → scan (RUNNING) → axe execution → COMPLETED → issues persisted →
details/issues APIs returned normalized findings → foreign-user access
rejected.

## 9. Known limitations (Module 3B)

- **Single-page scans**: `depth` is accepted but depth > 1 is not followed;
  `pages_scanned` is always 1 (crawling is a later module).
- **`xpath` / `css_path`** are empty — axe reports target selectors, not
  XPath; derivation is deferred.
- **Synchronous in-request background execution** via FastAPI
  BackgroundTasks: suitable for single-page scans now; a queue/worker +
  scheduler (the RUNNING partial index anticipates it) is the scale-up path.
- **Score** is a simple weighted heuristic, deliberately not
  Lighthouse-equivalent or ML-based.
- Playwright's bundled Chromium is not committed; environments must run
  `playwright install chromium` once (or set `AXE_BROWSER_CHANNEL` to an
  installed browser).

## 10. How to add another scanner (e.g. Lighthouse)

1. Create `app/scanners/lighthouse.py` implementing `BaseScanner`
   (`name`, `version`, `wcag_version`, `scanner_type`, `async scan(...)`).
2. Register it: `SCANNER_REGISTRY[ScannerType.LIGHTHOUSE] = LighthouseScanner`.
3. Done — the API/service accept `scanner_type: "LIGHTHOUSE"` unchanged
   (the CHECK constraint on `scans.scanner_type` already allows it).
