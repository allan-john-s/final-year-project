import { beforeEach, describe, expect, it, vi } from 'vitest'

import { strategyService, type GenerateStrategiesInput } from './strategyService'

vi.mock('@/lib/api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>

const generationRow = {
  metadata: {
    scan_id: 'scan-1',
    target_type: 'issue',
    issue_id: 'issue-1',
    group_id: null,
    context_version: '1.0',
    prompt_version: '1.0',
    provider: 'mock',
    model: 'mock-model',
    temperature: 0.2,
    strategy_count: 3,
    generated_at: '2026-08-15T00:00:00Z',
  },
  strategies: [
    {
      strategy_id: 'native-label',
      strategy_index: 1,
      issue_id: 'issue-1',
      group_id: null,
      context_version: '1.0',
      strategy_type: 'native_html',
      title: 'Use a native label',
      summary: 'Summary',
      rationale: 'Rationale',
      implementation_steps: ['Add a label'],
      expected_accessibility_impact: 'high',
      wcag_alignment: ['4.1.2'],
      implementation_effort: 'low',
      maintainability_notes: 'Low',
      compatibility_notes: 'Broad',
      risks: [],
      assumptions: ['Editable source'],
      confidence: 0.9,
      evidence_reference: 'issue-1',
    },
  ],
}

describe('strategyService', () => {
  beforeEach(() => {
    mockedPost.mockReset()
  })

  it('posts to the scan strategies endpoint with snake_case payload', async () => {
    mockedPost.mockResolvedValue({ data: generationRow })

    const input: GenerateStrategiesInput = { issueId: 'issue-1', strategyCount: 3 }
    await strategyService.generateStrategies('scan-1', input)

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/strategies', {
      issue_id: 'issue-1',
      group_id: null,
      strategy_count: 3,
    })
  })

  it('maps the response into camelCase models', async () => {
    mockedPost.mockResolvedValue({ data: generationRow })

    const result = await strategyService.generateStrategies('scan-1', { issueId: 'issue-1' })

    expect(result.metadata.scanId).toBe('scan-1')
    expect(result.metadata.provider).toBe('mock')
    expect(result.strategies).toHaveLength(1)
    const strategy = result.strategies[0]
    expect(strategy.strategyId).toBe('native-label')
    expect(strategy.strategyIndex).toBe(1)
    expect(strategy.strategyType).toBe('native_html')
    expect(strategy.wcagAlignment).toEqual(['4.1.2'])
    expect(strategy.implementationSteps).toEqual(['Add a label'])
    expect(strategy.evidenceReference).toBe('issue-1')
  })

  it('passes group targets and custom counts', async () => {
    mockedPost.mockResolvedValue({ data: generationRow })

    await strategyService.generateStrategies('scan-1', { groupId: 'rule:x', strategyCount: 5 })

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/strategies', {
      issue_id: null,
      group_id: 'rule:x',
      strategy_count: 5,
    })
  })

  it('defaults the strategy count to 3', async () => {
    mockedPost.mockResolvedValue({ data: generationRow })

    await strategyService.generateStrategies('scan-1', { issueId: 'issue-1' })

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/scans/scan-1/strategies',
      expect.objectContaining({ strategy_count: 3 }),
    )
  })

  it('propagates API errors', async () => {
    mockedPost.mockRejectedValue(new Error('The provider timed out.'))

    await expect(
      strategyService.generateStrategies('scan-1', { issueId: 'issue-1' }),
    ).rejects.toThrow('The provider timed out.')
  })
})
