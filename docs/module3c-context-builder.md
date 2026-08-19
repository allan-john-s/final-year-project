# Module 3C — Context Builder

> Module 3C builds the **bridge between detection and remediation**: it turns a
> completed scan's persisted data into a **deterministic, versioned,
> machine-readable ContextDocument** that future strategy-generation modules
> can consume reliably. It **does not** recommend fixes, generate strategies,
> call an LLM, or rank anything — it only prepares structured evidence.

## 1. Objective & why it exists

Scanners (axe, Lighthouse, …) detect violations. Our research contribution is
a *context-aware* framework that goes beyond detection: it preserves the
surrounding evidence (element, rule/WCAG, page, scan, project) so a later
module can choose remediation strategies based on *context*, not just on the
fact that a rule fired. The Context Builder is where that evidence is
assembled — deterministically and without inventing anything.

## 2. Architecture

```
GET /api/v1/scans/{scan_id}/context
  ↓  get_context_service (DI)
ContextBuilderService (app/context/services.py)
  ├── ScanRepository          → owned scan (404 IDOR-safe) + must be COMPLETED (409)
  ├── ProjectRepository       → owning project (defense-in-depth)
  ├── IssueRepository         → normalized issues for the scan
  ↓
ContextDocument (app/context/models.py)   ← pure construction, deterministic
```

`app/context/`:
```
models.py       # ContextDocument + Project/Scan/Page/Issue/Rule/Wcag/Element/Evidence/Group models
mapping.py      # isolated pure helpers: HTML snippet parsing + WCAG criterion/principle mapping
services.py     # ContextBuilderService + group_issues()
interfaces.py   # ContextBuilder protocol
exceptions.py   # ContextError / ContextUnavailableError (409)
```

The service never queries Supabase directly — it composes the existing
repositories, exactly like `ScanExecutionService`.

## 3. ContextDocument

```json
{
  "context_version": "1.0",
  "project":   { "project_id", "name", "description", "website_url", "status" },
  "scan":      { "scan_id", "scanner_type", "status", "scanner_name", "scanner_version",
                 "wcag_version", "scan_url", "scan_depth", "pages_scanned", "started_at",
                 "completed_at", "duration_ms", "total_dom_elements", "tested_elements",
                 "accessibility_score", "total_issues", "critical_count", "serious_count",
                 "moderate_count", "minor_count" },
  "page":      { "url", "hostname", "pathname", "title", "scanned_at", "duration_ms",
                 "scanner", "scanner_version", "total_issues", "…counts", "accessibility_score" },
  "issues":    [ IssueContext … ],
  "groups":    [ IssueGroup … ],
  "generated_at": "…"
}
```

- **Versioned**: `context_version = "1.0"`; future representations bump it
  (1.1, 2.0) without breaking consumers.
- **Explicit models, not dict soup**: every node is a typed Pydantic model.
- **No user identity**: `project_id` is the only ownership identifier; no
  `user_id`, tokens, or credentials anywhere.

## 4. IssueContext (per issue)

```json
{
  "issue_id", "scan_id", "project_id",
  "rule":     { "rule_id", "rule_name", "description", "help", "help_url", "impact",
                "tags", "wcag": { "wcag_version", "level", "tags", "criteria", "principle" } },
  "impact":   "SERIOUS",
  "wcag":     { … same as rule.wcag … },
  "element":  { "html", "tag", "attributes", "selector", "dom_path", "text_content",
                "role", "aria", "form", "surrounding_html", "parent_context" },
  "evidence": { "failure_summary", "xpath", "css_path", "screenshot_path", "affected_nodes" },
  "scanner_name", "scanner_version"
}
```

All original normalized issue fields are preserved verbatim (nothing is
dropped during transformation).

## 5. Element / HTML context

The scanner stores the affected HTML snippet + axe target. The Context Builder
adds a best-effort structured view (`app/context/mapping.py`):

- `tag` — the element name (`<p …>` → `p`),
- `attributes` — parsed attribute map,
- `aria` — `aria-*` attributes, `role` — the role attribute,
- `form` — form-related attributes (`name`, `type`, `placeholder`, …),
- `text_content` — whitespace-collapsed visible text (tags stripped).

This is **not** a general HTML parser: malformed/hostile snippets degrade to
empty fields, never to crashes, and everything is treated as opaque text.

## 6. WCAG context

Derived **only** from what axe reports (`tags`, `wcag_level`, scan
`wcag_version`):

- `level` = the issue's `wcag_level` (A/AA/AAA) — never invented,
- `criteria` = the `wcagNNNN` tags formatted deterministically
  (`wcag143` → `1.4.3`, `wcag1411` → `1.4.11`),
- `principle` = the standard WCAG principle of the first criterion
  (1 Perceivable / 2 Operable / 3 Understandable / 4 Robust) — an isolated,
  documented mapping; unknown principles → `null`.

## 7. Issue grouping (deterministic, explainable)

`group_issues()` in `app/context/services.py` produces stable groups:

| type | key | meaning |
| --- | --- | --- |
| `same_rule` | `rule:<rule_id>` | every issue of the same axe rule |
| `same_element` | `element:<selector>` | every issue targeting the same element |
| `wcag` | `wcag:<criterion>` | every issue sharing a WCAG criterion |

No ML, no embeddings, no LLM. Keys double as stable sort ids, so ordering is
fully reproducible.

## 8. Deterministic generation

- issues sorted by stable `issue_id`, groups sorted by `group_id`,
- tags and WCAG criteria sorted/deduplicated,
- **no random ids, no timestamps inside content** — `generated_at` is
  metadata only, so identical inputs produce byte-identical content
  (verified by a dedicated test).

## 9. API

`GET /api/v1/scans/{scan_id}/context` — JWT required.

| case | response |
| --- | --- |
| authenticated owner, COMPLETED scan | 200 `ContextDocument` |
| missing or foreign scan | 404 `scan_not_found` (IDOR-safe, no existence leak) |
| scan not completed (PENDING/RUNNING/FAILED) | 409 `context_unavailable` |
| malformed id | 422 |
| no token | 401 |

Context is generated on demand from the persisted rows — no extra CRUD
endpoints, no persistence.

## 10. Security review

- **IDOR**: scan lookup is scoped to the authenticated user (404 for
  foreign); project ownership is re-verified; a scan/project integrity break
  answers the same 404.
- **No secrets**: context contains no `user_id`, tokens, or credentials
  (test-enforced by walking the serialized document).
- **Untrusted HTML**: `element.html` and `text_content` are raw scanner
  output. The frontend renders them as **escaped text** inside
  `<pre>/<code>` (React escapes text content; no `dangerouslySetInnerHTML`),
  so a malicious page can never inject executable markup (verified by a
  test asserting no parsed `<img>` element appears).
- **Oversized/malformed values**: snippets were already capped at the model/
  DB layer (8000 chars) and parsing degrades safely.

## 11. Testing

| Suite | Coverage |
| --- | --- |
| `test_context_models.py` | required fields, version default, JSON round-trip, no-user-identity serialization |
| `test_context_mapping.py` | element tag/attributes/ARIA/form/text extraction, malformed input, WCAG criteria formatting (incl. 4-digit criteria), principle mapping |
| `test_context_service.py` | full build, ownership 404s, COMPLETED-only (409), empty/single/multi-issue scans, grouping determinism, stable ordering, malformed optional fields, scan/project mismatch |
| `test_context_api.py` | 401/200/404 foreign/404 missing/409 running/422, structure + no-secrets walk |

All deterministic, network-free, no Supabase credentials.

## 12. Limitations

- **Single-page scans** (inherited from 3B): `page.title`, `surrounding_html`
  and `parent_context` are reserved/empty until a later module captures them.
- **Element parsing is best-effort regex**, not a full HTML parser.
- **Principle mapping** covers the standard 4 principles only.
- Context is recomputed on demand (no caching) — fine at current scale; a
  cache/versioned snapshot may come later if research experiments need it.

## 13. Future AI integration

`ContextDocument` is the stable input contract for the future
**Strategy Generation** module: it carries the issue, the element evidence,
the rule/WCAG context, page/scan/project context, and deterministic groups —
everything a strategy module needs without re-parsing raw scan data. Adding a
new context shape later only means bumping `context_version` and extending
the builder; consumers version-check the document.
