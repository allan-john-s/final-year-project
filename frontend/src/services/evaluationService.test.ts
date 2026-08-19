import { beforeEach, describe, expect, it, vi } from 'vitest'

import { evaluationService, type EvaluateStrategiesInput } from './evaluationService'
import type { CandidateStrategy } from './strategyService'

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

const batchRow = {
  scan_id: 'scan-1',
  issue_id: 'issue-1',
  group_id: null,
  context_version: '1.0',
  evaluation_version: '1.0',
  prompt_version: '1.0',
  provider: 'mock',
  model: 'mock-model',
  evaluations: [
    {
      evaluation_id: 'eval-native-1',
      strategy_id: 'native-1',
      scan_id: 'scan-1',
      issue_id: 'issue-1',
      group_id: null,
      context_version: '1.0',
      evaluation_version: '1.0',
      accessibility_impact_score: 9,
      standards_compliance_score: 9,
      contextual_suitability_score: 8,
      implementation_effort_score: 8,
      maintainability_score: 9,
      compatibility_score: 9,
      risk_score: 8,
      strengths: ['Native semantics are robust.'],
      weaknesses: ['Styling may change.'],
      rationale: 'Native HTML is the most robust fix.',
      assumptions: ['Source is editable.'],
      uncertainties: ['Manual check still required.'],
      evidence_references: ['issue-1'],
      evaluator_provider: 'mock',
      evaluator_model: 'mock-model',
      prompt_version: '1.0',
      evaluated_at: '2026-08-16T00:00:00Z',
    },
  ],
}

describe('evaluationService', () => {
  beforeEach(() => {
    mockedPost.mockReset()
  })

  it('posts strategies with matching ids to the evaluations endpoint', async () => {
    mockedPost.mockResolvedValue({ data: batchRow })

    const input: EvaluateStrategiesInput = { issueId: 'issue-1', strategies: [STRATEGY] }
    await evaluationService.evaluateStrategies('scan-1', input)

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/evaluations', {
      issue_id: 'issue-1',
      group_id: null,
      strategy_ids: ['native-1'],
      strategies: [
        expect.objectContaining({
          strategy_id: 'native-1',
          issue_id: 'issue-1',
          strategy_type: 'native_html',
          implementation_steps: ['Add a label'],
          evidence_reference: 'issue-1',
        }),
      ],
    })
  })

  it('maps the response into camelCase evaluation models with all seven scores', async () => {
    mockedPost.mockResolvedValue({ data: batchRow })

    const result = await evaluationService.evaluateStrategies('scan-1', {
      issueId: 'issue-1',
      strategies: [STRATEGY],
    })

    expect(result.scanId).toBe('scan-1')
    expect(result.issueId).toBe('issue-1')
    expect(result.provider).toBe('mock')
    expect(result.evaluations).toHaveLength(1)
    const evaluation = result.evaluations[0]
    expect(evaluation.evaluationId).toBe('eval-native-1')
    expect(evaluation.strategyId).toBe('native-1')
    expect(evaluation.accessibilityImpactScore).toBe(9)
    expect(evaluation.standardsComplianceScore).toBe(9)
    expect(evaluation.contextualSuitabilityScore).toBe(8)
    expect(evaluation.implementationEffortScore).toBe(8)
    expect(evaluation.maintainabilityScore).toBe(9)
    expect(evaluation.compatibilityScore).toBe(9)
    expect(evaluation.riskScore).toBe(8)
    expect(evaluation.strengths).toEqual(['Native semantics are robust.'])
    expect(evaluation.weaknesses).toEqual(['Styling may change.'])
    expect(evaluation.evidenceReferences).toEqual(['issue-1'])
    expect(evaluation.evaluatorProvider).toBe('mock')
  })

  it('passes group targets', async () => {
    mockedPost.mockResolvedValue({ data: { ...batchRow, group_id: 'rule:x', issue_id: null } })

    await evaluationService.evaluateStrategies('scan-1', {
      groupId: 'rule:x',
      strategies: [{ ...STRATEGY, groupId: 'rule:x', evidenceReference: 'rule:x' }],
    })

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/evaluations', {
      issue_id: null,
      group_id: 'rule:x',
      strategy_ids: ['native-1'],
      strategies: [expect.objectContaining({ group_id: 'rule:x', evidence_reference: 'rule:x' })],
    })
  })

  it('propagates API errors', async () => {
    mockedPost.mockRejectedValue(new Error('The evaluation provider timed out.'))

    await expect(
      evaluationService.evaluateStrategies('scan-1', { issueId: 'issue-1', strategies: [STRATEGY] }),
    ).rejects.toThrow('The evaluation provider timed out.')
  })
})
