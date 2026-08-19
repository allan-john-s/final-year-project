/**
 * Evaluation service — the single place that talks to the evaluation API
 * (Module 5).
 *
 * POST /api/v1/scans/{scanId}/evaluations evaluates each supplied candidate
 * strategy INDEPENDENTLY across seven bounded 0–10 dimensions. Evaluations
 * are deliberately NOT ranked here — the API returns one evaluation per
 * strategy and no total/rank field; ranking belongs to Module 6. The UI must
 * therefore never label a strategy "best", "recommended" or "winner".
 *
 * Strategies are generated on demand (never persisted), so the request
 * carries the full candidate strategies alongside their ids; the backend
 * re-validates them against the deterministic context.
 */
import { apiClient } from '@/lib/api'
import type { CandidateStrategy } from '@/services/strategyService'

export interface StrategyEvaluation {
  evaluationId: string
  strategyId: string
  scanId: string
  issueId: string
  groupId: string | null
  contextVersion: string
  evaluationVersion: string
  accessibilityImpactScore: number
  standardsComplianceScore: number
  contextualSuitabilityScore: number
  implementationEffortScore: number
  maintainabilityScore: number
  compatibilityScore: number
  riskScore: number
  strengths: string[]
  weaknesses: string[]
  rationale: string
  assumptions: string[]
  uncertainties: string[]
  evidenceReferences: string[]
  evaluatorProvider: string
  evaluatorModel: string
  promptVersion: string
  evaluatedAt: string
}

export interface EvaluationBatch {
  scanId: string
  issueId: string | null
  groupId: string | null
  contextVersion: string
  evaluationVersion: string
  promptVersion: string
  provider: string
  model: string
  evaluations: StrategyEvaluation[]
}

export interface EvaluateStrategiesInput {
  issueId?: string
  groupId?: string
  strategies: CandidateStrategy[]
}

/** The seven evaluation dimensions in display order (label + score field). */
export const EVALUATION_CRITERIA: ReadonlyArray<{
  label: string
  score: (evaluation: StrategyEvaluation) => number
}> = [
  { label: 'Accessibility Impact', score: (e) => e.accessibilityImpactScore },
  { label: 'Standards Compliance', score: (e) => e.standardsComplianceScore },
  { label: 'Contextual Suitability', score: (e) => e.contextualSuitabilityScore },
  { label: 'Implementation Effort', score: (e) => e.implementationEffortScore },
  { label: 'Maintainability', score: (e) => e.maintainabilityScore },
  { label: 'Compatibility', score: (e) => e.compatibilityScore },
  { label: 'Risk', score: (e) => e.riskScore },
]

interface EvaluationRow {
  evaluation_id: string
  strategy_id: string
  scan_id: string
  issue_id: string
  group_id: string | null
  context_version: string
  evaluation_version: string
  accessibility_impact_score: number
  standards_compliance_score: number
  contextual_suitability_score: number
  implementation_effort_score: number
  maintainability_score: number
  compatibility_score: number
  risk_score: number
  strengths: string[]
  weaknesses: string[]
  rationale: string
  assumptions: string[]
  uncertainties: string[]
  evidence_references: string[]
  evaluator_provider: string
  evaluator_model: string
  prompt_version: string
  evaluated_at: string
}

interface BatchRow {
  scan_id: string
  issue_id: string | null
  group_id: string | null
  context_version: string
  evaluation_version: string
  prompt_version: string
  provider: string
  model: string
  evaluations: EvaluationRow[]
}

function mapEvaluation(row: EvaluationRow): StrategyEvaluation {
  return {
    evaluationId: row.evaluation_id,
    strategyId: row.strategy_id,
    scanId: row.scan_id,
    issueId: row.issue_id,
    groupId: row.group_id,
    contextVersion: row.context_version,
    evaluationVersion: row.evaluation_version,
    accessibilityImpactScore: row.accessibility_impact_score,
    standardsComplianceScore: row.standards_compliance_score,
    contextualSuitabilityScore: row.contextual_suitability_score,
    implementationEffortScore: row.implementation_effort_score,
    maintainabilityScore: row.maintainability_score,
    compatibilityScore: row.compatibility_score,
    riskScore: row.risk_score,
    strengths: row.strengths,
    weaknesses: row.weaknesses,
    rationale: row.rationale,
    assumptions: row.assumptions,
    uncertainties: row.uncertainties,
    evidenceReferences: row.evidence_references,
    evaluatorProvider: row.evaluator_provider,
    evaluatorModel: row.evaluator_model,
    promptVersion: row.prompt_version,
    evaluatedAt: row.evaluated_at,
  }
}

function strategyToRow(strategy: CandidateStrategy) {
  return {
    strategy_id: strategy.strategyId,
    strategy_index: strategy.strategyIndex,
    issue_id: strategy.issueId,
    group_id: strategy.groupId,
    context_version: strategy.contextVersion,
    strategy_type: strategy.strategyType,
    title: strategy.title,
    summary: strategy.summary,
    rationale: strategy.rationale,
    implementation_steps: strategy.implementationSteps,
    expected_accessibility_impact: strategy.expectedAccessibilityImpact,
    wcag_alignment: strategy.wcagAlignment,
    implementation_effort: strategy.implementationEffort,
    maintainability_notes: strategy.maintainabilityNotes,
    compatibility_notes: strategy.compatibilityNotes,
    risks: strategy.risks,
    assumptions: strategy.assumptions,
    confidence: strategy.confidence,
    evidence_reference: strategy.evidenceReference,
  }
}

class EvaluationService {
  /** Evaluate every supplied candidate strategy for an issue/group of a scan. */
  async evaluateStrategies(
    scanId: string,
    input: EvaluateStrategiesInput,
  ): Promise<EvaluationBatch> {
    const { data } = await apiClient.post<BatchRow>(`/api/v1/scans/${scanId}/evaluations`, {
      issue_id: input.issueId ?? null,
      group_id: input.groupId ?? null,
      strategy_ids: input.strategies.map((strategy) => strategy.strategyId),
      strategies: input.strategies.map(strategyToRow),
    })
    return {
      scanId: data.scan_id,
      issueId: data.issue_id,
      groupId: data.group_id,
      contextVersion: data.context_version,
      evaluationVersion: data.evaluation_version,
      promptVersion: data.prompt_version,
      provider: data.provider,
      model: data.model,
      evaluations: data.evaluations.map(mapEvaluation),
    }
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const evaluationService = new EvaluationService()
