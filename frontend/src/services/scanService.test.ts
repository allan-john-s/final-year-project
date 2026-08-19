import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/lib/api'

import { scanService } from './scanService'

vi.mock('@/lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedApi = vi.mocked(apiClient)

const SCAN_ROW = {
  id: 's-1',
  project_id: 'p-1',
  scanner_type: 'AXE',
  status: 'COMPLETED',
  started_at: '2026-08-14T10:00:00Z',
  completed_at: '2026-08-14T10:00:05Z',
  duration_ms: 4800,
  summary: { total_issues: 2 },
  total_issues: 2,
  critical_count: 0,
  serious_count: 1,
  moderate_count: 0,
  minor_count: 1,
  accessibility_score: 94,
  scanner_name: 'axe-core',
  scanner_version: '4.10.2',
  wcag_version: '2.2',
  scan_url: 'https://example.com',
  scan_depth: 1,
  pages_scanned: 1,
  browser_name: 'chromium',
  browser_version: '128.0.0.0',
  user_agent: 'agent',
  total_dom_elements: 40,
  tested_elements: 12,
  normalization_duration_ms: 20,
  persistence_duration_ms: 15,
  created_at: '2026-08-14T10:00:00Z',
}

const ISSUE_ROW = {
  id: 'i-1',
  scan_id: 's-1',
  rule_id: 'color-contrast',
  rule_name: 'Elements must have sufficient color contrast',
  description: 'Ensures contrast meets WCAG 2 AA thresholds',
  help: 'Elements must have sufficient color contrast',
  help_url: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
  impact: 'SERIOUS',
  wcag_level: 'AA',
  tags: ['wcag2aa', 'wcag143'],
  element_selector: '#main > p',
  html_snippet: '<p>Low contrast</p>',
  failure_summary: 'Fix any of the following: insufficient contrast',
  xpath: '',
  css_path: '',
  dom_path: '#main > p',
  screenshot_path: '',
  created_at: '2026-08-14T10:00:05Z',
}

describe('scanService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts a scan with the project id in the path and AXE default', async () => {
    mockedApi.post.mockResolvedValue({ data: { ...SCAN_ROW, status: 'RUNNING', started_at: '2026-08-14T10:00:00Z' } })

    const scan = await scanService.startScan('p-1')

    expect(mockedApi.post).toHaveBeenCalledWith('/api/v1/projects/p-1/scan', {
      scanner_type: 'AXE',
    })
    expect(scan.status).toBe('RUNNING')
    expect(scan.projectId).toBe('p-1')
  })

  it('lists scans and maps snake_case to camelCase', async () => {
    mockedApi.get.mockResolvedValue({ data: [SCAN_ROW] })

    const scans = await scanService.listScans()

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/scans')
    expect(scans[0]).toEqual({
      id: 's-1',
      projectId: 'p-1',
      scannerType: 'AXE',
      status: 'COMPLETED',
      startedAt: '2026-08-14T10:00:00Z',
      completedAt: '2026-08-14T10:00:05Z',
      durationMs: 4800,
      summary: { total_issues: 2 },
      totalIssues: 2,
      criticalCount: 0,
      seriousCount: 1,
      moderateCount: 0,
      minorCount: 1,
      accessibilityScore: 94,
      scannerName: 'axe-core',
      scannerVersion: '4.10.2',
      wcagVersion: '2.2',
      scanUrl: 'https://example.com',
      scanDepth: 1,
      pagesScanned: 1,
      browserName: 'chromium',
      browserVersion: '128.0.0.0',
      userAgent: 'agent',
      totalDomElements: 40,
      testedElements: 12,
      normalizationDurationMs: 20,
      persistenceDurationMs: 15,
      createdAt: '2026-08-14T10:00:00Z',
    })
  })

  it('fetches a project’s scans via the project path', async () => {
    mockedApi.get.mockResolvedValue({ data: [SCAN_ROW] })

    await scanService.listProjectScans('p-1')

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/projects/p-1/scans')
  })

  it('maps an issue row to the camelCase shape', async () => {
    mockedApi.get.mockResolvedValue({ data: [ISSUE_ROW] })

    const issues = await scanService.getIssues('s-1')

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/scans/s-1/issues')
    expect(issues[0]).toEqual({
      id: 'i-1',
      scanId: 's-1',
      ruleId: 'color-contrast',
      ruleName: 'Elements must have sufficient color contrast',
      description: 'Ensures contrast meets WCAG 2 AA thresholds',
      help: 'Elements must have sufficient color contrast',
      helpUrl: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
      impact: 'SERIOUS',
      wcagLevel: 'AA',
      tags: ['wcag2aa', 'wcag143'],
      elementSelector: '#main > p',
      htmlSnippet: '<p>Low contrast</p>',
      failureSummary: 'Fix any of the following: insufficient contrast',
      xpath: '',
      cssPath: '',
      domPath: '#main > p',
      screenshotPath: '',
      createdAt: '2026-08-14T10:00:05Z',
    })
  })

  it('deletes a scan', async () => {
    mockedApi.delete.mockResolvedValue({ data: undefined })

    await scanService.deleteScan('s-1')

    expect(mockedApi.delete).toHaveBeenCalledWith('/api/v1/scans/s-1')
  })
})
