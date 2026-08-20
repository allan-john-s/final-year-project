# Module 8 — Re-scan and Measure Accessibility Improvement

## Objective

Module 8 closes the verification loop by allowing the system to compare an original scan against a follow-up scan after an accepted remediation has supposedly been applied. It provides objective, deterministic verification of remediation effectiveness.

## Research Motivation

The research contribution is **objective verification**. Module 7 generates a remediation proposal and the developer applies it externally. Module 8 compares the before/after scan data to determine whether accessibility actually improved — without assuming the fix was applied or that it worked.

This enables future research experiments measuring:

- Strategy effectiveness
- Remediation success rates
- Context-aware ranking quality
- Severity reduction patterns

## Architecture

```
backend/app/measurements/
    __init__.py          — module exports
    models.py            — data models, fingerprints, severity burden, classification
    interfaces.py        — MeasurementStore and ScanAccessor abstract interfaces
    services.py          — MeasurementService (core comparison logic)
    store.py             — InMemoryMeasurementStore (dev persistence)
    exceptions.py        — measurement-specific exceptions

backend/app/schemas/measurements.py     — Pydantic request/response schemas
backend/app/dependencies/measurements.py — FastAPI dependency injection
backend/app/api/routes/measurements.py   — REST endpoints

frontend/src/services/measurementService.ts — API client
frontend/src/hooks/useMeasurements.ts       — React Query hooks
frontend/src/pages/ContextPage.tsx           — measurement UI section
```

## Data Model

### ImprovementMeasurement

| Field | Type | Description |
|---|---|---|
| id | string | Unique measurement ID |
| remediation_id | string | Associated remediation proposal |
| original_scan_id | string | Original scan before remediation |
| followup_scan_id | string | Follow-up scan after remediation |
| original_accessibility_score | float? | Original scan score |
| followup_accessibility_score | float? | Follow-up scan score |
| score_delta | float? | followup − original |
| score_improvement_percentage | float? | Percentage improvement relative to original |
| original_issue_count | int | Total issues in original scan |
| followup_issue_count | int | Total issues in follow-up scan |
| issues_resolved | int | Issues present in original but not in follow-up |
| issues_remaining | int | Issues present in both scans |
| new_issues_introduced | int | Issues present in follow-up but not original |
| critical_before / critical_after | int | Critical issue counts |
| serious_before / serious_after | int | Serious issue counts |
| moderate_before / moderate_after | int | Moderate issue counts |
| minor_before / minor_after | int | Minor issue counts |
| status | MeasurementStatus | Classification result |
| measurement_summary | string | Human-readable summary |
| created_at | datetime | When measurement was created |

### MeasurementStatus

| Status | Interpretation |
|---|---|
| IMPROVED | Score increased significantly, or severity burden decreased without regressions |
| NO_CHANGE | No meaningful measurable difference within threshold |
| REGRESSED | Score decreased significantly, or new severe issues introduced |
| COMPLETED | Measurement performed but result does not fit a simple category (e.g. no scores available) |

## Issue Comparison Algorithm

### Fingerprinting

Each issue is fingerprinted using a deterministic SHA-256 hash of:

- `rule_id` (e.g. `color-contrast`)
- `selector` (CSS selector of the affected element)
- `dom_path` (DOM path of the affected element)
- `impact` (severity level)

This allows the system to identify which issues were resolved, which persist, and which are newly introduced — without assuming every missing issue was "fixed."

### Comparison

```
original_fingerprints  = {fingerprint(issue) for issue in original_scan.issues}
followup_fingerprints  = {fingerprint(issue) for issue in followup_scan.issues}

resolved        = original_fingerprints − followup_fingerprints
persistent      = original_fingerprints ∩ followup_fingerprints
newly_introduced = followup_fingerprints − original_fingerprints

issues_resolved = len(resolved)
issues_remaining = len(persistent)
new_issues_introduced = len(newly_introduced)
```

## Severity Comparison

Before/after counts are produced for each severity level: critical, serious, moderate, minor.

### Severity Burden

A weighted severity burden is calculated for comparison:

| Severity | Weight |
|---|---|
| CRITICAL | 10 |
| SERIOUS | 5 |
| MODERATE | 2 |
| MINOR | 1 |

`total_burden = critical × 10 + serious × 5 + moderate × 2 + minor × 1`

## Score Calculation

```
score_delta = followup_score − original_score

if original_score > 0:
    improvement_percentage = (score_delta / original_score) × 100
elif followup_score > 0:
    improvement_percentage = 100.0  # Special case: 0 → positive
else:
    improvement_percentage = 0.0
```

## Improvement Classification Rules

Deterministic, in priority order:

1. **REGRESSED**: score decreased beyond threshold (−0.5) AND new severe issues exist
2. **REGRESSED**: score decreased beyond threshold AND severity burden increased
3. **IMPROVED**: score increased beyond threshold (+0.5) AND no new severe issues
4. **IMPROVED**: severity burden decreased significantly (>20%) without new severe issues
5. **IMPROVED**: small positive score change (>0) AND severity burden decreased
6. **NO_CHANGE**: within threshold range (−0.5 to +0.5) with no severity changes
7. **COMPLETED**: no scores available (both None)

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/remediations/{remediation_id}/measure` | Create a measurement |
| GET | `/api/v1/remediations/{remediation_id}/measurements` | List measurements for a remediation |
| GET | `/api/v1/measurements/{measurement_id}` | Get a specific measurement |

### POST /api/v1/remediations/{remediation_id}/measure

**Request:**
```json
{
  "followup_scan_id": "scan-followup-id"
}
```

**Response:** `ImprovementMeasurement`

**Validation rules:**
- Remediation must exist and belong to the authenticated user
- Remediation status must be ACCEPTED or APPLIED
- Follow-up scan must exist and belong to the same user
- Follow-up scan must be completed
- Follow-up scan must be created after the original scan
- No duplicate measurement for the same remediation + follow-up scan pair

## Frontend

Integrated into `ContextPage.tsx` as a new section after remediation proposal display.

### UI Flow

1. Developer generates remediation proposal (Module 7)
2. Developer applies the fix externally
3. Developer runs a new scan
4. Developer enters the follow-up scan ID
5. System creates a measurement comparing original vs follow-up scan
6. Before/After report is displayed

### Display Elements

- **Status badge**: IMPROVED ✅ / NO_CHANGE ➖ / REGRESSED ⚠️ / COMPLETED ✔️
- **Measurement summary**: human-readable description
- **Before card**: original scan score, issue counts, severity breakdown
- **After card**: follow-up scan score, issue counts, severity breakdown
- **Issue comparison**: resolved / remaining / new counts
- **Score change**: delta and percentage
- **Disclaimer**: measurement does not assume the fix was applied

### Important UX

The UI explicitly states: **"Accepted remediation does NOT mean verified improvement."** Only the follow-up scan determines whether accessibility actually improved.

## Security

- Authenticated access required
- Remediation ownership validated
- Follow-up scan ownership validated
- No user_id accepted from client
- No secrets exposed
- Foreign-user isolation tested

## Testing

### Backend Tests (53 tests)

- Model validation
- Fingerprint determinism
- Severity burden calculation
- Classification rules (improved, no-change, regressed, completed)
- Score edge cases (zero original, None scores)
- Service success cases
- Service error cases (missing remediation, invalid status, incomplete scan, scan order, duplicates)
- API authentication
- API success/error responses
- Ownership validation

### Frontend Tests

- measurementService.test.ts: API mapping, CRUD operations
- ContextPage.test.tsx: mock integration for measurement hooks

## Limitations

- In-memory persistence only (not safe for concurrent production use)
- Fingerprinting relies on rule_id + selector + dom_path — may not perfectly match issues across different scanners
- No automatic source-code modification
- No re-scanning triggered from the application
- Measurement depends on external scan completion

## Future Work

- Database persistence via Supabase migration
- Automatic scan triggering after remediation
- Historical trend analysis across multiple remediations
- Integration with Module 7 for full pipeline automation
- Research experiment framework for measuring effectiveness
