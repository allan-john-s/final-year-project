import { beforeEach, describe, expect, it, vi } from 'vitest'

import { rankingService, type RankStrategiesInput } from './rankingService'
import type { CandidateStrategy } from '@/services/strategyService'
import type { StrategyEvaluation } from '@/services/evaluationService'

vi.mock('@/lib/api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>

const STRATEGY: CandidateStrategy = {
  strategyId: 'native-1',
  strategyIndex: 1,
  issueId: 'issue-1',
  groupId: null,
  contextVersion: '1.0',
  strategyType: 'native_html',
  title: 'Use a native label',
  summary: 'Summary',
  rationale: 'Rationale',
  implementationSteps: ['Add a label'],
  expectedAccessibilityImpact: 'high',
  wcagAlignment: ['4.1.2'],
  implementationEffort: 'low',
  maintainabilityNotes: 'Low',
  compatibilityNotes: 'Broad',
  risks: [],
  assumptions: ['Editable source'],
  confidence: 0.9,
  evidenceReference: 'issue-1',
}

const EVALUATION: StrategyEvaluation = {
  evaluationId: 'eval-native-1',
  strategyId: 'native-1',
  scanId: 'scan-1',
  issueId: 'issue-1',
  groupId: null,
  contextVersion: '1.0',
  evaluationVersion: '1.0',
  accessibilityImpactScore: 9,
  standardsComplianceScore: 9,
  contextualSuitabilityScore: 8,
  implementationEffortScore: 8,
  maintainabilityScore: 9,
  compatibilityScore: 9,
  riskScore: 8,
  strengths: ['Strong.'],
  weaknesses: ['Minor.'],
  rationale: 'Rationale.',
  assumptions: [],
  uncertainties: [],
  evidenceReferences: ['issue-1'],
  evaluatorProvider: 'mock',
  evaluatorModel: 'mock-model',
  promptVersion: '1.0',
  evaluatedAt: '2026-08-16T00:00:00Z',
}

const rankingBatchRow = {
  scan_id: 'scan-1',
  issue_id: 'issue-1',
  group_id: null,
  context_version: '1.0',
  ranking_version: '1.0',
  ranking_method: 'contextual',
  weights_used: {
    accessibility_impact: 0.2,
    standards_compliance: 0.15,
    contextual_suitability: 0.15,
    // The backend serializes the weight under `implementation_effort` —
    // NOT `implementation_effort_score` (score suffix is used only for the
    // seven evaluation dimensions). Mapping the wrong key made the weight
    // undefined and crashed the weights panel's `.toFixed()` call.
    implementation_effort: 0.15,
    maintainability: 0.1,
    compatibility: 0.1,
    risk: 0.15,
  },
  context_factors: [
    {
      factor: 'critical_wcag_issue',
      detected: true,
      influence: 0.3,
      affected_dimensions: ['accessibility_impact'],
      explanation: 'Critical issue detected.',
    },
  ],
  ranked_strategies: [
    {
      strategy_id: 'native-1',
      rank: 1,
      weighted_score: 8.5,
      dimension_scores: {
        accessibility_impact: 9,
        standards_compliance: 9,
        contextual_suitability: 8,
        implementation_effort: 8,
        maintainability: 9,
        compatibility: 9,
        risk: 8,
      },
      strengths: ['Strong.'],
      weaknesses: ['Minor.'],
      ranking_explanation: 'Ranked first because of high scores.',
      confidence: 0.9,
    },
  ],
  generated_at: '2026-08-17T00:00:00Z',
}

describe('rankingService', () => {
  beforeEach(() => {
    mockedPost.mockReset()
  })

  it('posts strategies and evaluations to the ranking endpoint', async () => {
    mockedPost.mockResolvedValue({ data: rankingBatchRow })

    const input: RankStrategiesInput = {
      issueId: 'issue-1',
      strategies: [STRATEGY],
      evaluations: [EVALUATION],
      mode: 'contextual',
    }
    await rankingService.rankStrategies('scan-1', input)

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/ranking', {
      issue_id: 'issue-1',
      group_id: null,
      strategy_ids: ['native-1'],
      strategies: [expect.objectContaining({ strategy_id: 'native-1' })],
      evaluations: [expect.objectContaining({ strategy_id: 'native-1' })],
      mode: 'contextual',
    })
  })

  it('maps the response into camelCase ranking models', async () => {
    mockedPost.mockResolvedValue({ data: rankingBatchRow })

    const result = await rankingService.rankStrategies('scan-1', {
      issueId: 'issue-1',
      strategies: [STRATEGY],
      evaluations: [EVALUATION],
    })

    expect(result.scanId).toBe('scan-1')
    expect(result.issueId).toBe('issue-1')
    expect(result.rankingMethod).toBe('contextual')
    expect(result.weightsUsed.accessibilityImpact).toBe(0.2)
    expect(result.weightsUsed.standardsCompliance).toBe(0.15)
    expect(result.weightsUsed.contextualSuitability).toBe(0.15)
    // Regression: the implementation-effort weight must be mapped from the
    // real backend key, not silently become undefined.
    expect(result.weightsUsed.implementationEffort).toBe(0.15)
    expect(result.weightsUsed.maintainability).toBe(0.1)
    expect(result.weightsUsed.compatibility).toBe(0.1)
    expect(result.weightsUsed.risk).toBe(0.15)
    expect(result.contextFactors).toHaveLength(1)
    expect(result.contextFactors[0].factor).toBe('critical_wcag_issue')
    expect(result.contextFactors[0].detected).toBe(true)
    expect(result.rankedStrategies).toHaveLength(1)
    expect(result.rankedStrategies[0].strategyId).toBe('native-1')
    expect(result.rankedStrategies[0].rank).toBe(1)
    expect(result.rankedStrategies[0].weightedScore).toBe(8.5)
    expect(result.rankedStrategies[0].rankingExplanation).toBe('Ranked first because of high scores.')
    expect(result.rankedStrategies[0].strengths).toEqual(['Strong.'])
    expect(result.rankedStrategies[0].dimensionScores.accessibility_impact).toBe(9)
  })

  it('defaults mode to contextual', async () => {
    mockedPost.mockResolvedValue({ data: rankingBatchRow })

    await rankingService.rankStrategies('scan-1', {
      issueId: 'issue-1',
      strategies: [STRATEGY],
      evaluations: [EVALUATION],
    })

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/scans/scan-1/ranking',
      expect.objectContaining({ mode: 'contextual' }),
    )
  })

  it('propagates API errors', async () => {
    mockedPost.mockRejectedValue(new Error('The ranking service timed out.'))

    await expect(
      rankingService.rankStrategies('scan-1', {
        issueId: 'issue-1',
        strategies: [STRATEGY],
        evaluations: [EVALUATION],
      }),
    ).rejects.toThrow('The ranking service timed out.')
  })
})
