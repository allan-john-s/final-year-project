import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { useScan, useScanIssues } from '@/hooks/useScans'
import { createAuthValue } from '@/test/authValue'

import { ScanDetailsPage } from './ScanDetailsPage'

vi.mock('@/hooks/useScans', () => ({
  useScan: vi.fn(),
  useScanIssues: vi.fn(),
}))

vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))

const mockedUseScan = vi.mocked(useScan)
const mockedUseScanIssues = vi.mocked(useScanIssues)
const mockedUseAuth = vi.mocked(useAuth)

function makeScan(overrides: Record<string, unknown> = {}) {
  return {
    id: 's-1',
    projectId: 'p-1',
    scannerType: 'AXE',
    status: 'COMPLETED',
    startedAt: '2026-08-14T10:00:00Z',
    completedAt: '2026-08-14T10:00:05Z',
    durationMs: 4800,
    summary: { total_issues: 1 },
    totalIssues: 1,
    criticalCount: 0,
    seriousCount: 1,
    moderateCount: 0,
    minorCount: 0,
    accessibilityScore: 95,
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
    ...overrides,
  }
}

const ISSUE = {
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
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/p-1/scans/s-1']}>
      <ScanDetailsPage />
    </MemoryRouter>,
  )
}

describe('ScanDetailsPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))
    mockedUseScan.mockReturnValue({
      data: makeScan(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    mockedUseScanIssues.mockReturnValue({
      data: [ISSUE],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)
  })

  it('renders a completed scan with score, counts and metadata', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Accessibility scan' })).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('95')).toBeInTheDocument()
    expect(screen.getByText('1 serious')).toBeInTheDocument()
    expect(screen.getByText('1 total')).toBeInTheDocument()
    expect(screen.getByText(/axe-core/)).toBeInTheDocument()
    expect(screen.getByText('2.2')).toBeInTheDocument()
  })

  it('lists normalized issues with their guidance', () => {
    renderPage()

    expect(screen.getByText('Elements must have sufficient color contrast')).toBeInTheDocument()
    expect(screen.getByText('color-contrast')).toBeInTheDocument()
    expect(screen.getByText('Serious')).toBeInTheDocument()
    expect(screen.getByText(/Fix any of the following/)).toBeInTheDocument()
    expect(screen.getByText(/Low contrast/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Learn more' })).toHaveAttribute(
      'href',
      'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
    )
  })

  it('shows the running state while a scan is in progress', () => {
    mockedUseScan.mockReturnValue({
      data: makeScan({ status: 'RUNNING', accessibilityScore: null }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    renderPage()

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('surfaces the sanitized failure message on a failed scan', () => {
    mockedUseScan.mockReturnValue({
      data: makeScan({ status: 'FAILED', summary: { error: 'Timed out loading the target' } }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    renderPage()

    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Timed out loading the target')
  })

  it('shows an error state when the scan cannot be loaded', () => {
    mockedUseScan.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Scan not found.'),
      refetch: vi.fn(),
    } as never)

    renderPage()

    expect(screen.getByText('Scan unavailable')).toBeInTheDocument()
    expect(screen.getByText('Scan not found.')).toBeInTheDocument()
  })
})
