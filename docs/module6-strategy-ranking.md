# Module 6 — Context-Aware Strategy Ranking

Status: **COMPLETE**

## 1. Objective

Module 6 ranks evaluated candidate remediation strategies (Module 5) using
transparent, context-aware weighted scoring. It produces an ordered list of
strategies with explainable scores, enabling the system to identify the most
suitable strategy for a specific accessibility issue and project context.

The pipeline becomes:

```
ContextDocument
      ↓
Candidate Strategies        (Module 4)
      ↓
Evaluation of EACH strategy (Module 5)
      ↓
Module 6 — Context-Aware Ranking
      ↓
Ranked strategies + recommended strategy
      ↓
Module 7 — Remediation       (NOT implemented here)
```

## 2. Research motivation

The research contribution is a *context-aware multi-strategy framework*. Module 6
answers not only

> "Which strategy has the best evaluation scores?"

but

> "Which strategy is most suitable for **THIS** issue given the **specific
> context** — critical WCAG violations, deep DOM nesting, high issue
> frequency, and low accessibility score?"

The system provides two ranking modes — **baseline** (equal weights) and
**contextual** (adjusted weights) — so future experiments can measure whether
contextual information changes recommendations.

Module 6 deliberately does NOT:

- modify source code
- execute remediation
- automatically commit changes
- perform re-scans

## 3. Architecture

```
POST /api/v1/scans/{scan_id}/ranking
  → StrategyRankingService         (target resolution, context factor detection)
      → ContextBuilder (ContextBuilderService)   (ownership 404-safe, COMPLETED-only 409)
      → detect_context_factors()    (deterministic, from ContextDocument only)
      → apply_contextual_weights()  (adjust baseline weights)
      → rank_strategies()           (weighted scoring + ordering)
      → generate_explanation()      (human-readable ranking rationale)
      → RankingBatch                (metadata + ranked strategies)
```

The API never instantiates a model or calls an LLM. The ranking algorithm is
pure, deterministic, and fully testable.

## 4. Seven evaluation dimensions

All seven dimensions share the same direction: **higher is better**.

| Dimension | 10 means | 0 means |
|---|---|---|
| Accessibility Impact | excellent | extremely poor |
| Standards Compliance | excellent | extremely poor |
| Contextual Suitability | excellent | extremely poor |
| Implementation Effort | very easy / very low effort | extremely difficult / very high |
| Maintainability | excellent | extremely poor |
| Compatibility | excellent | extremely poor |
| Risk | very low risk | very high risk |

The effort and risk semantics are already inverted by Module 5 — the ranking
algorithm requires no inversions.

## 5. Baseline ranking

Baseline mode uses fixed, equal weights across all seven dimensions:

| Dimension | Weight |
|---|---|
| Accessibility Impact | 1/7 ≈ 0.1429 |
| Standards Compliance | 1/7 ≈ 0.1429 |
| Contextual Suitability | 1/7 ≈ 0.1429 |
| Implementation Effort | 1/7 ≈ 0.1429 |
| Maintainability | 1/7 ≈ 0.1429 |
| Compatibility | 1/7 ≈ 0.1429 |
| Risk | 1/7 ≈ 0.1429 |

This produces a simple arithmetic mean of the seven scores — a fair comparison
without contextual bias.

## 6. Context-aware ranking

Contextual mode adjusts the baseline weights based on deterministic factors
detected from the ContextDocument. After adjustment, weights are re-normalized
to sum to 1.0.

The weighted score is:

```
weighted_score = Σ(score_i × weight_i)  for i in 7 dimensions
```

## 7. Weight calculation

Weights are validated:

- Every weight ≥ 0 and ≤ 1.0
- Total weight = 1.0 (±0.001 tolerance)
- Weights are rounded to 4 decimal places to prevent floating-point drift

## 8. Context factors

Factors are derived **exclusively** from information present in the
ContextDocument. No factors are invented.

| Factor | Trigger | Affected dimensions | Influence |
|---|---|---|---|
| `critical_wcag_issue` | Issue impact is CRITICAL or SERIOUS | accessibility_impact, standards_compliance | +0.30 |
| `wcag_level_a` | Issue violates WCAG Level A | standards_compliance, accessibility_impact | +0.20 |
| `complex_dom` | DOM nesting depth > 5 | maintainability, compatibility | +0.20 |
| `high_issue_frequency` | Scan has > 10 total issues | implementation_effort, maintainability | +0.15 |
| `multiple_severe_issues` | Critical + serious count > 3 | accessibility_impact, standards_compliance | +0.25 |
| `low_accessibility_score` | Accessibility score < 60 | accessibility_impact, contextual_suitability | +0.20 |

All factors are detected deterministically — no randomization, no LLM.

## 9. Score normalization

After contextual adjustment, weights are re-normalized to sum to 1.0:

```
normalized_weight_i = adjusted_weight_i / Σ(adjusted_weights)
```

This ensures the weighted score remains in [0.0, 10.0] regardless of
the number of detected factors.

## 10. Score direction

All seven Module 5 dimensions use the same direction (higher = better).
The ranking algorithm therefore requires no inversions or special handling.
This is validated by the Module 5 documentation and tests.

## 11. Ranking explanation

Every ranked strategy receives a human-readable explanation covering:

- The rank position and weighted score
- The top contributing dimensions (score × weight)
- Any detected context factors that influenced the weights
- The overall reasoning for the ranking

Example:

> Strategy #1 ranked 1st out of 3 with a weighted score of 8.50/10. The
> highest contributing dimensions were: accessibility impact (9/10 × 20.00%
> = 1.80); standards compliance (9/10 × 15.00% = 1.35). Context-aware
> factors influenced the ranking: critical wcag issue.

## 12. Baseline vs contextual comparison

The frontend supports comparing baseline and contextual rankings for the same
strategies. This enables the research question:

> Does contextual information change the recommended strategy?

When the order changes between baseline and contextual, the UI highlights this
and explains the difference. When the order is the same, the UI confirms
contextual factors did not alter the recommendation.

## 13. Security

- Authenticated access required (JWT).
- Scan ownership validated (IDOR-safe — foreign scans return 404).
- Issue/group ownership validated.
- No `user_id` accepted from client (identity from JWT).
- No secrets exposed in ranking response.
- All ranking data is computed on demand — no persistence of sensitive data.

## 14. Testing

Backend (66 new tests, all deterministic):

- **Models** — weight validation (sum, bounds, rounding), ranking mode enum,
  context factor fields, ranked strategy fields, no-secrets guarantee.
- **Algorithms** — weighted scoring (equal/custom/extreme weights), context
  factor detection (critical, high frequency, low score, multiple severe),
  contextual weight adjustment (renormalization, direction), ranking order,
  tie handling, determinism, explanation generation.
- **Service** — target resolution (issue/group), ownership (404-safe),
  non-completed scans (409), baseline vs contextual, comparison, no-evaluations
  (409), determinism, no-secrets guarantee.
- **API** — 401/200/404/409/422 paths, payload guarantees, mode default,
  recommendation language, no-secrets.

Frontend (4 new tests):

- Ranking API call and response mapping, mode default, error propagation.

All Module 0–5 tests remain green (455 backend / 102 frontend).

## 15. Limitations

- Ranking is generated **on demand** and not persisted (by design).
- The contextual weight adjustment rules are deterministic but manually
  designed — future work could use research-driven weight optimization.
- The ranking algorithm is a linear weighted sum — more complex algorithms
  (e.g., TOPSIS, AHP) could be explored in future research modules.
- Context factor triggers (thresholds like > 10 issues, score < 60) are
  configurable research parameters that may be tuned.

## 16. Future remediation integration

Module 7 will consume the ranked strategies from Module 6 to apply the
recommended remediation. The design keeps ranking and remediation separate so
each stage is independently testable and reproducible.

---

**Module 6 ranks candidate strategies.**

It does **NOT**:

- modify source code
- execute remediation
- automatically commit changes
- perform re-scans
- use an LLM for ranking
