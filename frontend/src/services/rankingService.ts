/**
 * Ranking service — the single place that talks to the ranking API (Module 6).
 *
 * POST /api/v1/scans/{scanId}/ranking ranks evaluated candidate strategies
 * using transparent, context-aware weighted scoring. The ranking is fully
 * deterministic and does not call an LLM.
 *
 * Follows the evaluationService convention: components and hooks depend on
 * this module (never axios directly) and requests go through `@/lib/api`,
 * which attaches the Supabase bearer token.
 */
import { apiClient } from '@/lib/api'
import type { CandidateStrategy } from '@/services/strategyService'
import type { StrategyEvaluation } from '@/services/evaluationService'

export type RankingMode = 'baseline' | 'contextual'

export interface RankingWeights {
  accessibilityImpact: number
  standardsCompliance: number
  contextualSuitability: number
  implementationEffort: number
  maintainability: number
  compatibility: number
  risk: number
}

export interface ContextFactor {
  factor: string
  detected: boolean
  influence: number
  affectedDimensions: string[]
  explanation: string
}

export interface RankedStrategy {
  strategyId: string
  rank: number
  weightedScore: number
  dimensionScores: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  rankingExplanation: string
  confidence: number
}

export interface RankingBatch {
  scanId: string
  issueId: string | null
  groupId: string | null
  contextVersion: string
  rankingVersion: string
  rankingMethod: string
  weightsUsed: RankingWeights
  contextFactors: ContextFactor[]
  rankedStrategies: RankedStrategy[]
  generatedAt: string
}

export interface RankStrategiesInput {
  issueId?: string
  groupId?: string
  strategies: CandidateStrategy[]
  evaluations: StrategyEvaluation[]
  mode?: RankingMode
}

interface WeightsRow {
  accessibility_impact: number
  standards_compliance: number
  contextual_suitability: number
  implementation_effort: number
  maintainability: number
  compatibility: number
  risk: number
}

interface ContextFactorRow {
  factor: string
  detected: boolean
  influence: number
  affected_dimensions: string[]
  explanation: string
}

interface RankedStrategyRow {
  strategy_id: string
  rank: number
  weighted_score: number
  dimension_scores: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  ranking_explanation: string
  confidence: number
}

interface RankingBatchRow {
  scan_id: string
  issue_id: string | null
  group_id: string | null
  context_version: string
  ranking_version: string
  ranking_method: string
  weights_used: WeightsRow
  context_factors: ContextFactorRow[]
  ranked_strategies: RankedStrategyRow[]
  generated_at: string
}

function mapWeights(row: WeightsRow): RankingWeights {
  return {
    accessibilityImpact: row.accessibility_impact,
    standardsCompliance: row.standards_compliance,
    contextualSuitability: row.contextual_suitability,
    implementationEffort: row.implementation_effort,
    maintainability: row.maintainability,
    compatibility: row.compatibility,
    risk: row.risk,
  }
}

function mapContextFactor(row: ContextFactorRow): ContextFactor {
  return {
    factor: row.factor,
    detected: row.detected,
    influence: row.influence,
    affectedDimensions: row.affected_dimensions,
    explanation: row.explanation,
  }
}

function mapRankedStrategy(row: RankedStrategyRow): RankedStrategy {
  return {
    strategyId: row.strategy_id,
    rank: row.rank,
    weightedScore: row.weighted_score,
    dimensionScores: row.dimension_scores,
    strengths: row.strengths,
    weaknesses: row.weaknesses,
    rankingExplanation: row.ranking_explanation,
    confidence: row.confidence,
  }
}

function mapBatch(row: RankingBatchRow): RankingBatch {
  return {
    scanId: row.scan_id,
    issueId: row.issue_id,
    groupId: row.group_id,
    contextVersion: row.context_version,
    rankingVersion: row.ranking_version,
    rankingMethod: row.ranking_method,
    weightsUsed: mapWeights(row.weights_used),
    contextFactors: row.context_factors.map(mapContextFactor),
    rankedStrategies: row.ranked_strategies.map(mapRankedStrategy),
    generatedAt: row.generated_at,
  }
}

function evaluationToRow(e: StrategyEvaluation) {
  return {
    evaluation_id: e.evaluationId,
    strategy_id: e.strategyId,
    scan_id: e.scanId,
    issue_id: e.issueId,
    group_id: e.groupId,
    context_version: e.contextVersion,
    evaluation_version: e.evaluationVersion,
    accessibility_impact_score: e.accessibilityImpactScore,
    standards_compliance_score: e.standardsComplianceScore,
    contextual_suitability_score: e.contextualSuitabilityScore,
    implementation_effort_score: e.implementationEffortScore,
    maintainability_score: e.maintainabilityScore,
    compatibility_score: e.compatibilityScore,
    risk_score: e.riskScore,
    strengths: e.strengths,
    weaknesses: e.weaknesses,
    rationale: e.rationale,
    assumptions: e.assumptions,
    uncertainties: e.uncertainties,
    evidence_references: e.evidenceReferences,
    evaluator_provider: e.evaluatorProvider,
    evaluator_model: e.evaluatorModel,
    prompt_version: e.promptVersion,
    evaluated_at: e.evaluatedAt,
  }
}

function strategyToRow(s: CandidateStrategy) {
  return {
    strategy_id: s.strategyId,
    strategy_index: s.strategyIndex,
    issue_id: s.issueId,
    group_id: s.groupId,
    context_version: s.contextVersion,
    strategy_type: s.strategyType,
    title: s.title,
    summary: s.summary,
    rationale: s.rationale,
    implementation_steps: s.implementationSteps,
    expected_accessibility_impact: s.expectedAccessibilityImpact,
    wcag_alignment: s.wcagAlignment,
    implementation_effort: s.implementationEffort,
    maintainability_notes: s.maintainabilityNotes,
    compatibility_notes: s.compatibilityNotes,
    risks: s.risks,
    assumptions: s.assumptions,
    confidence: s.confidence,
    evidence_reference: s.evidenceReference,
  }
}

class RankingService {
  /** Rank evaluated strategies for an issue/group of a scan. */
  async rankStrategies(
    scanId: string,
    input: RankStrategiesInput,
  ): Promise<RankingBatch> {
    const { data } = await apiClient.post<RankingBatchRow>(
      `/api/v1/scans/${scanId}/ranking`,
      {
        issue_id: input.issueId ?? null,
        group_id: input.groupId ?? null,
        strategy_ids: input.strategies.map((s) => s.strategyId),
        strategies: input.strategies.map(strategyToRow),
        evaluations: input.evaluations.map(evaluationToRow),
        mode: input.mode ?? 'contextual',
      },
    )
    return mapBatch(data)
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const rankingService = new RankingService()
