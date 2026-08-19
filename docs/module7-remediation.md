# Module 7 — Remediation

## 1. Objective

Module 7 produces a **structured, reviewable remediation proposal** for the top-ranked accessibility strategy identified by Module 6. It consumes the output of all previous pipeline stages — scan results, context document, candidate strategies, evaluations, and ranking — and generates an actionable proposal that a developer can review, accept, or reject.

## 2. Research Motivation

The research pipeline separates concerns across distinct stages:

- **Module 4**: Generate multiple candidate remediation strategies
- **Module 5**: Evaluate each strategy across seven dimensions
- **Module 6**: Rank strategies using context-aware weighted scoring
- **Module 7**: Produce a concrete remediation proposal for the recommended strategy

Module 7 does NOT combine these stages. It deliberately consumes the Module 6 recommendation as input, maintaining the separation of concerns that enables research comparison of different strategies.

## 3. Architecture

```
backend/app/remediations/
    __init__.py           # Domain exports
    models.py             # RemediationProposal, ProposedChange, status lifecycle
    interfaces.py         # RemediationProvider protocol
    services.py           # RemediationService — orchestrates proposal generation
    exceptions.py         # Domain-specific error types
    store.py              # In-memory persistence (dev/test)
    providers/
        __init__.py
        mock.py           # MockRemediationProvider — deterministic, no LLM

backend/app/schemas/remediations.py   # API request/response schemas
backend/app/dependencies/remediations.py  # FastAPI DI wiring
backend/app/api/routes/remediations.py    # API endpoints
```

## 4. Relationship to Module 6

Module 7 requires the **recommended (rank #1) strategy** from Module 6. The service:

1. Validates that the strategy exists in the supplied list
2. Verifies the strategy belongs to the specified issue
3. Verifies the strategy was evaluated
4. Re-runs the ranking algorithm to confirm the strategy is rank #1
5. Delegates proposal generation to the provider

If the strategy is not rank #1, the service rejects the request with `strategy_not_recommended` (409).

## 5. Provider Abstraction

### RemediationProvider Protocol

```python
class RemediationProvider(Protocol):
    name: str
    async def generate_proposal(
        self,
        *,
        scan_id: str,
        issue_id: str,
        strategy_id: str,
        rank: int,
        issue_description: str,
        strategy_title: str,
        strategy_summary: str,
        strategy_rationale: str,
        implementation_steps: list[str],
        element_html: str,
        element_selector: str,
        wcag_criteria: list[str],
    ) -> RemediationProposal: ...
```

### MockRemediationProvider

- Fully deterministic (same inputs → same output)
- No LLM dependency
- No network calls
- Produces realistic proposals with before/after code changes
- Used for development and testing

## 6. Proposal Structure

Each `RemediationProposal` contains:

| Field | Description |
|---|---|
| `id` | Unique proposal identifier |
| `scan_id` | Source scan |
| `issue_id` | Target accessibility issue |
| `strategy_id` | Recommended strategy being applied |
| `rank` | Strategy's rank position |
| `title` | Human-readable proposal title |
| `summary` | Brief summary of the proposed fix |
| `rationale` | Why this strategy was recommended |
| `implementation_steps` | Ordered steps to apply the fix |
| `proposed_change` | BEFORE/AFTER code comparison |
| `affected_element` | CSS selector of the affected element |
| `expected_improvement` | Expected accessibility improvement |
| `risks` | Potential side effects |
| `validation_steps` | How to verify the fix works |
| `provider` | Which provider generated the proposal |
| `confidence` | Provider confidence (0.0–1.0) |
| `status` | Current lifecycle status |

## 7. Review-First Workflow

Module 7 explicitly does NOT automatically modify source code. The workflow is:

```
Ranked recommendation
        ↓
Generate proposal
        ↓
Developer reviews proposal
        ↓
Accept / Reject
        ↓
Only explicitly accepted proposals can reach APPLIED status
```

**Module 7 does NOT:**
- Modify source code automatically
- Create commits
- Create pull requests
- Perform re-scans

## 8. Status Lifecycle

```
PROPOSED → REVIEWED → ACCEPTED → APPLIED
                   ↘ REJECTED
```

Valid transitions are enforced by the service. Invalid transitions return 409.

## 9. Security

- Authentication required for all endpoints
- Scan ownership validated through ContextBuilderService
- Strategy must belong to the specified issue
- No `user_id` accepted from the client
- No secrets exposed in responses

## 10. Persistence

Module 7 uses an **in-memory store** (`RemediationStore`) for development and testing. In production, this would be replaced by a Supabase-backed repository with RLS.

The in-memory store is NOT safe for concurrent access in production — it's intended for single-process development and testing only.

### Future Database Migration

When persistence is needed, create:

```sql
CREATE TABLE public.remediation_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES public.scans(id) ON DELETE CASCADE,
    issue_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    rationale TEXT NOT NULL,
    implementation_steps JSONB NOT NULL DEFAULT '[]',
    proposed_change JSONB NOT NULL,
    affected_element TEXT NOT NULL DEFAULT '',
    expected_improvement TEXT NOT NULL,
    risks JSONB NOT NULL DEFAULT '[]',
    validation_steps JSONB NOT NULL DEFAULT '[]',
    provider TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    rank INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.remediation_proposals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own remediation proposals"
    ON public.remediation_proposals
    FOR ALL
    USING (auth.uid() = user_id);
```

**This migration must be manually applied in Supabase SQL Editor.**

## 11. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/scans/{scan_id}/remediation` | Generate a remediation proposal |
| GET | `/api/v1/scans/{scan_id}/remediations` | List proposals for a scan |
| GET | `/api/v1/remediations/{remediation_id}` | Get a specific proposal |
| PATCH | `/api/v1/remediations/{remediation_id}/status` | Update proposal status |

## 12. Frontend

The frontend adds to the existing StrategySection in ContextPage:

- **Generate Remediation** button appears after ranking
- Generates a proposal for the recommended (rank #1) strategy
- Displays the proposal with before/after code, implementation steps, and validation requirements
- Status update buttons (Mark Reviewed, Accept, Reject) are available via the API

## 13. Testing

### Backend Tests (53 new)

- `test_remediation_models.py`: Model validation, field bounds, status transitions, schemas
- `test_remediation_service.py`: Proposal generation, ownership validation, error cases, provider failure, deterministic output
- `test_remediation_api.py`: API endpoints, authentication, validation, retrieval, status updates, security

### Frontend Tests (6 new)

- `remediationService.test.ts`: Service mapping, API calls, error handling
- `ContextPage.test.tsx`: Updated with remediation hook mocks

## 14. Limitations

- **In-memory persistence**: Proposals are not persisted across server restarts
- **No automatic code modification**: The proposal is review-only
- **No re-scanning**: Module 7 does not verify the fix works
- **No Git integration**: No commits or PRs are created
- **Single provider**: Only the mock provider is implemented; real LLM providers require API keys

## 15. Future Possibilities

- Real LLM provider (OpenAI, Azure, local models) for proposal generation
- Automatic source-code patch generation
- Git integration for creating branches and PRs
- Re-scanning after fix application (Module 8)
- Human feedback loop for improving proposals
- Multi-file fix proposals for complex issues
