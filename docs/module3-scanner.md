# Module 3A — Scanner Architecture & Database Foundation

> Module 3A ships the **architecture and persistence foundation** for the
> accessibility scanning subsystem — nothing more. It defines the scanner
> contract, the normalized result model, the controlled scan lifecycle, and
> the Supabase tables (with strict RLS) that future engines will write to.
> **No scanner engine (Axe, Lighthouse, …), no scan execution, and no AI is
> implemented in this batch.**

```
Project
  ↓ 1:N (projects.user_id → auth.users.id, ON DELETE CASCADE)
Scan
  ↓ 1:N (scans.id → accessibility_issues.scan_id, ON DELETE CASCADE)
AccessibilityIssue
```

## 1. Scanner architecture

```
app/scanners/
    __init__.py        # barrel
    models.py          # ScannerType, Impact, WcagLevel, ScanMetadata,
                       # ScanTiming, AccessibilityIssue, NormalizedScanResult
    base.py            # BaseScanner (abstract contract)
    factory.py         # SCANNER_REGISTRY + get_scanner()

app/scans/             # persistence domain for the future pipeline
    models.py          # ScanStatus, Scan, ScanCreate, ScanUpdate
    interfaces.py      # ScanRepository (protocol)
    exceptions.py      # ScanError hierarchy (uniform {code, message} envelope)
app/repositories/scans.py   # SupabaseScanRepository (PostgREST, service-role key)
app/schemas/scans.py        # ScanCreateRequest / ScanUpdateRequest / ScanResponse
app/dependencies/scans.py   # get_scan_repository (DI seam)
```

### `BaseScanner` responsibility

`BaseScanner` (ABC) is the **only** contract between scanner engines and the
application:

- identity — `name`, `version`, `wcag_version`, `scanner_type` class
  attributes,
- `async scan(url, *, depth=1) -> NormalizedScanResult` — run the engine
  against a URL and return the normalized result.

The API/service/persistence layers depend on this interface, **never** on a
concrete engine, so Axe, Lighthouse, Pa11y, WAVE, or a custom research scanner
can be added later purely by implementing the contract and registering it in
`SCANNER_REGISTRY` — no other code changes.

### Factory / registry

```python
get_scanner(ScannerType.AXE)          # → ScannerUnavailableError (Module 3A)
get_scanner(ScannerType.RESEARCH)     # → instance, once an engine registers
available_scanners()                  # → [] in Module 3A
```

Module 3A registers **no engines** — any lookup answers
`ScannerUnavailableError` until Module 3B ships the first one. A fake engine
in the test suite proves the extension point works.

## 2. Normalized result model

Every engine returns a `NormalizedScanResult`:

```
NormalizedScanResult
├── metadata: ScanMetadata
│     scanner_name, scanner_type (enum), scanner_version, wcag_version,
│     scan_url, scan_depth, pages_scanned, browser_name, browser_version,
│     user_agent, total_dom_elements, tested_elements
├── timing: ScanTiming
│     duration_ms, normalization_duration_ms
└── issues: [AccessibilityIssue]
      rule_id, rule_name, description, help, help_url,
      impact (enum: CRITICAL/SERIOUS/MODERATE/MINOR), wcag_level (A/AA/AAA),
      tags, element_selector, html_snippet, failure_summary,
      xpath, css_path, dom_path, screenshot_path
```

- **Severity is controlled** — `Impact` enum, rejected at the Pydantic layer
  (and by a DB CHECK constraint); arbitrary strings never enter the system.
- Summary counts (`total_issues`, `critical_count`, …) are **derived** from
  `issues` via `result.summary()`, so they can never disagree with the data.
- The model is fully serializable (JSON round-trip tested) and carries every
  raw scanner field a future **Context Builder** needs — no AI fields exist
  yet by design.

## 3. Scan lifecycle

`ScanStatus` is a controlled enum mirrored by a DB CHECK constraint:

```
PENDING → RUNNING → COMPLETED
                 ↘ FAILED
```

`CANCELLED` is deliberately **not** modelled yet. Arbitrary values are
rejected at the domain layer (Pydantic) and the database layer (CHECK).

## 4. Database tables

### `public.scans`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | default `gen_random_uuid()` |
| `project_id` | uuid FK → `projects.id` | `ON DELETE CASCADE` |
| `user_id` | uuid FK → `auth.users.id` | `ON DELETE CASCADE` |
| `scanner_type` | text | CHECK `AXE/LIGHTHOUSE/PA11Y/WAVE/RESEARCH` |
| `status` | text | CHECK `PENDING/RUNNING/COMPLETED/FAILED`, default `PENDING` |
| `started_at` / `completed_at` | timestamptz | nullable (a PENDING scan hasn't started) |
| `duration_ms` | bigint | nullable, `>= 0` |
| `summary` | jsonb | default `{}` |
| `total_issues`, `critical_count`, `serious_count`, `moderate_count`, `minor_count` | integer | default 0, `>= 0` |
| `accessibility_score` | numeric(5,2) | nullable, 0–100 |
| scanner metadata | text/integer | `scanner_name`, `scanner_version`, `wcag_version`, `scan_url`, `scan_depth`, `pages_scanned`, `browser_name`, `browser_version`, `user_agent`, `total_dom_elements`, `tested_elements`, `normalization_duration_ms`, `persistence_duration_ms` |
| `created_at` | timestamptz | default `now()` |

### `public.accessibility_issues`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | default `gen_random_uuid()` |
| `scan_id` | uuid FK → `scans.id` | `ON DELETE CASCADE` |
| `rule_id`, `rule_name` | text NOT NULL | identity of the finding |
| `description`, `help`, `help_url` | text NOT NULL default `''` | |
| `impact` | text NOT NULL | CHECK `CRITICAL/SERIOUS/MODERATE/MINOR` |
| `wcag_level` | text | nullable, CHECK `A/AA/AAA` |
| `tags` | jsonb | default `[]` |
| `element_selector`, `html_snippet`, `failure_summary`, `xpath`, `css_path`, `dom_path`, `screenshot_path` | text NOT NULL default `''` | length-checked |

### Indexes

- `scans (user_id, created_at desc)` — "my scans, newest first"
- `scans (project_id, created_at desc)` — project drill-down
- `scans (status) WHERE status = 'RUNNING'` — partial index for the future
  scheduler's poll query (full `(status)` is low-selectivity, hence partial)
- `accessibility_issues (scan_id, impact)` — per-scan lookups (incl. FK
  cascade deletes) + impact-count aggregation in one index

## 5. Ownership model

```
auth user
    ↓  (auth.uid() = user_id)
projects.user_id
    ↓  (scans.user_id / project_id)
scans
    ↓  (accessibility_issues.scan_id)
accessibility_issues
```

Ownership is enforced in **three layers** (defense in depth):

1. **Database (RLS)** — every policy keys on `auth.uid()`; see §6.
2. **Repository** — every PostgREST query filters `user_id=eq.<uid>` (and
   `project_id` where relevant) even though the service-role key bypasses RLS.
3. **Domain** — `user_id` is never part of any request body or update model;
   creation commands always carry the owner explicitly.

## 6. RLS strategy

Both tables have RLS **enabled** with policies `to authenticated` only.

**`scans`** — SELECT/UPDATE/DELETE keyed on `auth.uid() = user_id`. The
**INSERT** policy is the critical one:

```sql
with check (
    auth.uid() = user_id
    and exists (
        select 1 from public.projects p
        where p.id = project_id and p.user_id = auth.uid()
    )
)
```

A malicious user cannot create a scan referencing another user's project
(the `exists` subquery fails), and cannot write a `user_id` that isn't their
own. The **UPDATE** policy repeats both checks so a scan can move through its
lifecycle (status/timings/counts) but **ownership can never be reassigned** —
`user_id` stays the caller and `project_id` must keep pointing at a project
the caller owns.

**`accessibility_issues`** — every policy verifies the referenced scan
belongs to the caller:

```sql
exists (select 1 from public.scans s where s.id = scan_id and s.user_id = auth.uid())
```

so issues can never be read from, inserted into, moved to, or deleted from
another user's scan.

## 7. Repository layer

`SupabaseScanRepository` (`app/repositories/scans.py`) mirrors the project
repository: PostgREST CRUD with the service-role key, ownership filters on
every query, row → `Scan` mapping, sanitized error messages, and a config
check before any network call (`ScanConfigurationError` → 503 when Supabase
is unconfigured). The `ScanRepository` protocol keeps the service/API layers
storage-agnostic and test-injectable.

No scan execution happens in Module 3A: the repository exposes the
persistence primitives (create/get/list/update/delete) that the future
pipeline will drive, plus the mapping helpers
(`ScanCreate.with_result`, `ScanUpdate.from_result`) that turn a
`NormalizedScanResult` into a persisted row.

## 8. Extension points (future modules)

- **New scanner engine** → implement `BaseScanner`, register the class in
  `SCANNER_REGISTRY` (Module 3B: Axe/Lighthouse; later Pa11y/WAVE/research).
- **Scan execution** → the pipeline service consumes `BaseScanner` +
  `ScanRepository`; no API change required (`app/schemas/scans.py` and
  `app/dependencies/scans.py` are already shaped).
- **Context Builder** → consumes `AccessibilityIssue` (all raw fields typed
  and serializable); no schema change required.
- **Issue persistence** → `accessibility_issues` is ready with a cascade and
  the `(scan_id, impact)` index; a future `AccessibilityIssueRepository`
  mirrors `SupabaseScanRepository`.

## 9. Intentionally NOT implemented in Module 3A

- ❌ Any scanner engine (Axe, Lighthouse, Pa11y, WAVE, research)
- ❌ Scan execution / scheduling / `POST /api/v1/scans` routes
- ❌ Fake scan results or demo data
- ❌ Context Builder, LLM/AI remediation, strategy generation, evaluation,
  ranking, explanation, apply-fix, re-scanning
- ❌ `CANCELLED` scan status
- ❌ Any change to Modules 0–2 (auth, projects) or the existing API surface

## 10. Migration handling

Migrations are **not run automatically** — this repo has no migration runner.
To apply this batch:

1. Open the Supabase Dashboard → SQL Editor.
2. Paste the contents of
   `supabase/migrations/20260814000001_create_scans_and_issues.sql`.
3. Run it (idempotent: extension guard, `drop`-free creation).

Until it is applied, the scans persistence layer answers
`scan_configuration_error`-style failures; projects/auth are unaffected.

## 11. Testing

| Suite | Coverage |
| --- | --- |
| `test_scanner_models.py` | metadata/URL validation, controlled `ScannerType`/`Impact`/`WcagLevel` enums, invalid severity/level rejection, issue validation, JSON round-trip, summary-count derivation |
| `test_scan_models.py` | controlled `ScanStatus` (incl. `CANCELLED` absence), ownership-required creation, negative count/score rejection, result → persistence mapping (`with_result`/`from_result`, never reassigns ownership) |
| `test_scanner_factory.py` | empty registry in 3A, `ScannerUnavailableError` for every type, fake-engine registration extension point |
| `test_scan_repository.py` | fake-transport PostgREST calls: create body + ownership, query scoping (`user_id=eq.` on every op), list filters/order, update/delete semantics, config-required-before-network, sanitized errors |

All tests are deterministic, network-free, and need no Supabase credentials
(the conftest `isolated_settings` fixture neutralizes any local `.env`).
