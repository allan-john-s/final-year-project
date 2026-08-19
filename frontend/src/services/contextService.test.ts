import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/lib/api'

import { contextService } from './contextService'

vi.mock('@/lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedApi = vi.mocked(apiClient)

const DOCUMENT_ROW = {
  context_version: '1.0',
  project: {
    project_id: 'p-1',
    name: 'Homepage',
    description: 'Our main site',
    website_url: 'https://example.com',
    status: 'SCANNED',
  },
  scan: {
    scan_id: 's-1',
    project_id: 'p-1',
    scanner_type: 'AXE',
    status: 'COMPLETED',
    scanner_name: 'axe-core',
    scanner_version: '4.10.2',
    wcag_version: '2.2',
    scan_url: 'https://example.com',
    scan_depth: 1,
    pages_scanned: 1,
    started_at: '2026-08-14T10:00:00Z',
    completed_at: '2026-08-14T10:00:05Z',
    duration_ms: 4800,
    total_dom_elements: 40,
    tested_elements: 12,
    accessibility_score: 94,
    total_issues: 1,
    critical_count: 0,
    serious_count: 1,
    moderate_count: 0,
    minor_count: 0,
  },
  page: {
    url: 'https://example.com',
    hostname: 'example.com',
    pathname: '/',
    title: '',
    scanned_at: '2026-08-14T10:00:05Z',
    duration_ms: 4800,
    scanner: 'axe-core',
    scanner_version: '4.10.2',
    total_issues: 1,
    critical_count: 0,
    serious_count: 1,
    moderate_count: 0,
    minor_count: 0,
    accessibility_score: 94,
  },
  issues: [
    {
      issue_id: 'i-1',
      scan_id: 's-1',
      project_id: 'p-1',
      rule: {
        rule_id: 'color-contrast',
        rule_name: 'Elements must have sufficient color contrast',
        description: 'Ensures contrast meets WCAG 2 AA thresholds',
        help: 'Elements must have sufficient color contrast',
        help_url: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
        impact: 'SERIOUS',
        tags: ['wcag2aa', 'wcag143'],
        wcag: {
          wcag_version: '2.2',
          level: 'AA',
          tags: ['wcag2aa', 'wcag143'],
          criteria: ['1.4.3'],
          principle: 'Perceivable',
        },
      },
      impact: 'SERIOUS',
      wcag: {
        wcag_version: '2.2',
        level: 'AA',
        tags: ['wcag2aa', 'wcag143'],
        criteria: ['1.4.3'],
        principle: 'Perceivable',
      },
      element: {
        html: '<p class="muted">Low contrast</p>',
        tag: 'p',
        attributes: { class: 'muted' },
        selector: '#main > p',
        dom_path: '#main > p',
        text_content: 'Low contrast',
        role: null,
        aria: {},
        form: {},
        surrounding_html: '',
        parent_context: '',
      },
      evidence: {
        failure_summary: 'Fix any of the following: insufficient contrast',
        xpath: '',
        css_path: '',
        screenshot_path: '',
        affected_nodes: 1,
      },
      scanner_name: 'axe-core',
      scanner_version: '4.10.2',
    },
  ],
  groups: [
    { group_id: 'rule:color-contrast', group_type: 'same_rule', label: 'Color contrast', issue_ids: ['i-1'] },
    { group_id: 'wcag:1.4.3', group_type: 'wcag', label: 'WCAG 1.4.3', issue_ids: ['i-1'] },
  ],
  generated_at: '2026-08-14T10:00:06Z',
}

describe('contextService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches context for a scan', async () => {
    mockedApi.get.mockResolvedValue({ data: DOCUMENT_ROW })

    const context = await contextService.getContext('s-1')

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/scans/s-1/context')
    expect(context.contextVersion).toBe('1.0')
    expect(context.project).toEqual({
      projectId: 'p-1',
      name: 'Homepage',
      description: 'Our main site',
      websiteUrl: 'https://example.com',
      status: 'SCANNED',
    })
    expect(context.scan.scanId).toBe('s-1')
    expect(context.scan.totalIssues).toBe(1)
    expect(context.page.hostname).toBe('example.com')
    expect(context.page.accessibilityScore).toBe(94)
  })

  it('maps issue context including rule, wcag and element evidence', async () => {
    mockedApi.get.mockResolvedValue({ data: DOCUMENT_ROW })

    const context = await contextService.getContext('s-1')

    const issue = context.issues[0]
    expect(issue.issueId).toBe('i-1')
    expect(issue.rule.ruleId).toBe('color-contrast')
    expect(issue.rule.wcag.criteria).toEqual(['1.4.3'])
    expect(issue.wcag.principle).toBe('Perceivable')
    expect(issue.element.tag).toBe('p')
    expect(issue.element.attributes).toEqual({ class: 'muted' })
    expect(issue.element.textContent).toBe('Low contrast')
    expect(issue.evidence.failureSummary).toContain('insufficient contrast')
  })

  it('maps groups with stable identifiers', async () => {
    mockedApi.get.mockResolvedValue({ data: DOCUMENT_ROW })

    const context = await contextService.getContext('s-1')

    expect(context.groups.map((g) => g.groupId)).toEqual(['rule:color-contrast', 'wcag:1.4.3'])
    expect(context.groups[0].issueIds).toEqual(['i-1'])
  })

  it('keeps HTML evidence as plain text (never parsed as markup)', async () => {
    mockedApi.get.mockResolvedValue({ data: DOCUMENT_ROW })

    const context = await contextService.getContext('s-1')

    expect(context.issues[0].element.html).toBe('<p class="muted">Low contrast</p>')
  })
})
