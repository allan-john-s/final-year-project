/**
 * Tests for the remediation service (Module 7).
 *
 * Verifies: proposal generation, retrieval, listing, status updates,
 * error handling, and the snake_case ↔ camelCase mapping.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api'

import { remediationService } from './remediationService'

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>
const mockedGet = apiClient.get as ReturnType<typeof vi.fn>
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>

const mockProposalRowSnake = {
  id: 'rem-abc123',
  scan_id: 'scan-1',
  issue_id: 'issue-1',
  strategy_id: 's-1',
  rank: 1,
  title: 'Fix color contrast',
  summary: 'Add sufficient contrast to the text.',
  rationale: 'The recommended strategy addresses the issue.',
  implementation_steps: ['Locate element', 'Update CSS'],
  proposed_change: {
    before: '<p>Low contrast</p>',
    after: '<p style="color: #333">High contrast</p>',
    file_path: 'src/style.css',
    line_number: 42,
    explanation: 'Changed text color.',
  },
  affected_element: '#main > p',
  expected_improvement: 'Resolves WCAG 1.4.3.',
  risks: ['Visual change'],
  validation_steps: ['Run axe'],
  provider: 'mock',
  confidence: 0.85,
  status: 'PROPOSED',
  remediation_version: '1.0',
  created_at: '2026-08-16T00:00:00Z',
  updated_at: '2026-08-16T00:00:00Z',
}

describe('RemediationService', () => {
  beforeEach(() => {
    mockedPost.mockReset()
    mockedGet.mockReset()
    mockedPatch.mockReset()
  })

  describe('generateRemediation', () => {
    it('posts to the correct endpoint and maps response', async () => {
      mockedPost.mockResolvedValue({ data: mockProposalRowSnake })

      const result = await remediationService.generateRemediation('scan-1', {
        issueId: 'issue-1',
        strategyId: 's-1',
        strategies: [],
        evaluations: [],
      })

      expect(mockedPost).toHaveBeenCalledWith('/api/v1/scans/scan-1/remediation', {
        issue_id: 'issue-1',
        strategy_id: 's-1',
        strategies: [],
        evaluations: [],
      })
      expect(result.id).toBe('rem-abc123')
      expect(result.scanId).toBe('scan-1')
      expect(result.issueId).toBe('issue-1')
      expect(result.strategyId).toBe('s-1')
      expect(result.rank).toBe(1)
      expect(result.status).toBe('PROPOSED')
      expect(result.proposedChange.before).toBe('<p>Low contrast</p>')
      expect(result.proposedChange.after).toContain('High contrast')
      expect(result.proposedChange.filePath).toBe('src/style.css')
      expect(result.proposedChange.lineNumber).toBe(42)
      expect(result.implementationSteps).toEqual(['Locate element', 'Update CSS'])
      expect(result.validationSteps).toEqual(['Run axe'])
      expect(result.confidence).toBe(0.85)
    })
  })

  describe('getRemediation', () => {
    it('fetches a proposal by ID', async () => {
      mockedGet.mockResolvedValue({ data: mockProposalRowSnake })

      const result = await remediationService.getRemediation('rem-abc123')

      expect(mockedGet).toHaveBeenCalledWith('/api/v1/remediations/rem-abc123')
      expect(result.id).toBe('rem-abc123')
      expect(result.title).toBe('Fix color contrast')
    })
  })

  describe('listRemediations', () => {
    it('returns an array of proposals', async () => {
      mockedGet.mockResolvedValue({ data: [mockProposalRowSnake] })

      const result = await remediationService.listRemediations('scan-1')

      expect(mockedGet).toHaveBeenCalledWith('/api/v1/scans/scan-1/remediations')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('rem-abc123')
    })

    it('returns empty array when no proposals exist', async () => {
      mockedGet.mockResolvedValue({ data: [] })

      const result = await remediationService.listRemediations('scan-empty')
      expect(result).toHaveLength(0)
    })
  })

  describe('updateStatus', () => {
    it('updates a proposal status', async () => {
      const reviewedSnake = { ...mockProposalRowSnake, status: 'REVIEWED' }
      mockedPatch.mockResolvedValue({ data: reviewedSnake })

      const result = await remediationService.updateStatus('rem-abc123', 'REVIEWED')

      expect(mockedPatch).toHaveBeenCalledWith('/api/v1/remediations/rem-abc123/status', {
        status: 'REVIEWED',
      })
      expect(result.status).toBe('REVIEWED')
    })
  })

  describe('error handling', () => {
    it('propagates API errors', async () => {
      mockedGet.mockRejectedValue(new Error('Network error'))

      await expect(
        remediationService.getRemediation('nonexistent'),
      ).rejects.toThrow('Network error')
    })
  })
})
