/**
 * Strategy generation service — the single place that talks to the strategy
 * API (Module 4).
 *
 * POST /api/v1/scans/{scanId}/strategies generates 2–5 *candidate*
 * remediation strategies for one accessibility issue or one deterministic
 * issue group. Candidates are intentionally NOT ranked — evaluation and
 * ranking belong to later modules, so the UI must never label one "best".
 *
 * Follows the contextService convention: components and hooks depend on this
 * module (never axios directly) and requests go through `@/lib/api`, which
 * attaches the Supabase bearer token.
 */
import { apiClient } from '@/lib/api'

export type StrategyType =
  | 'native_html'
  | 'aria'
  | 'structural'
  | 'content'
  | 'behavioral'
  | 'visual'
  | 'alternative'
  | 'other'

export type EffortRating = 'low' | 'medium' | 'high'
export type ImpactRating = 'low' | 'medium' | 'high'

export interface CandidateStrategy {
  strategyId: string
  strategyIndex: number
  issueId: string
  groupId: string | null
  contextVersion: string
  strategyType: StrategyType
  title: string
  summary: string
  rationale: string
  implementationSteps: string[]
  expectedAccessibilityImpact: ImpactRating
  wcagAlignment: string[]
  implementationEffort: EffortRating
  maintainabilityNotes: string
  compatibilityNotes: string
  risks: string[]
  assumptions: string[]
  confidence: number
  evidenceReference: string
}

export interface StrategyGenerationMetadata {
  scanId: string
  targetType: 'issue' | 'group'
  issueId: string | null
  groupId: string | null
  contextVersion: string
  promptVersion: string
  provider: string
  model: string
  temperature: number
  strategyCount: number
  generatedAt: string
}

export interface StrategyGeneration {
  metadata: StrategyGenerationMetadata
  strategies: CandidateStrategy[]
}

export interface GenerateStrategiesInput {
  issueId?: string
  groupId?: string
  strategyCount?: number
}

interface StrategyRow {
  strategy_id: string
  strategy_index: number
  issue_id: string
  group_id: string | null
  context_version: string
  strategy_type: StrategyType
  title: string
  summary: string
  rationale: string
  implementation_steps: string[]
  expected_accessibility_impact: ImpactRating
  wcag_alignment: string[]
  implementation_effort: EffortRating
  maintainability_notes: string
  compatibility_notes: string
  risks: string[]
  assumptions: string[]
  confidence: number
  evidence_reference: string
}

interface MetadataRow {
  scan_id: string
  target_type: 'issue' | 'group'
  issue_id: string | null
  group_id: string | null
  context_version: string
  prompt_version: string
  provider: string
  model: string
  temperature: number
  strategy_count: number
  generated_at: string
}

interface GenerationRow {
  metadata: MetadataRow
  strategies: StrategyRow[]
}

function mapStrategy(row: StrategyRow): CandidateStrategy {
  return {
    strategyId: row.strategy_id,
    strategyIndex: row.strategy_index,
    issueId: row.issue_id,
    groupId: row.group_id,
    contextVersion: row.context_version,
    strategyType: row.strategy_type,
    title: row.title,
    summary: row.summary,
    rationale: row.rationale,
    implementationSteps: row.implementation_steps,
    expectedAccessibilityImpact: row.expected_accessibility_impact,
    wcagAlignment: row.wcag_alignment,
    implementationEffort: row.implementation_effort,
    maintainabilityNotes: row.maintainability_notes,
    compatibilityNotes: row.compatibility_notes,
    risks: row.risks,
    assumptions: row.assumptions,
    confidence: row.confidence,
    evidenceReference: row.evidence_reference,
  }
}

class StrategyService {
  /** Generate candidate strategies for an issue or group of a scan. */
  async generateStrategies(
    scanId: string,
    input: GenerateStrategiesInput,
  ): Promise<StrategyGeneration> {
    const { data } = await apiClient.post<GenerationRow>(`/api/v1/scans/${scanId}/strategies`, {
      issue_id: input.issueId ?? null,
      group_id: input.groupId ?? null,
      strategy_count: input.strategyCount ?? 3,
    })
    return {
      metadata: {
        scanId: data.metadata.scan_id,
        targetType: data.metadata.target_type,
        issueId: data.metadata.issue_id,
        groupId: data.metadata.group_id,
        contextVersion: data.metadata.context_version,
        promptVersion: data.metadata.prompt_version,
        provider: data.metadata.provider,
        model: data.metadata.model,
        temperature: data.metadata.temperature,
        strategyCount: data.metadata.strategy_count,
        generatedAt: data.metadata.generated_at,
      },
      strategies: data.strategies.map(mapStrategy),
    }
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const strategyService = new StrategyService()
