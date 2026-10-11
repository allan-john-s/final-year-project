import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { useContextDocument } from '@/hooks/useContext'
import { useEvaluateStrategies } from '@/hooks/useEvaluations'
import { useGenerateStrategies } from '@/hooks/useStrategies'
import { useRankStrategies } from '@/hooks/useRankings'
import { useGenerateRemediation, useRemediations, useUpdateRemediationStatus } from '@/hooks/useRemediations'
import { useCreateMeasurement } from '@/hooks/useMeasurements'
import { createAuthValue } from '@/test/authValue'
import type { EvaluationBatch } from '@/services/evaluationService'
import type { RankingBatch } from '@/services/rankingService'
import type { CandidateStrategy, StrategyGeneration } from '@/services/strategyService'
import type {
  GenerateRemediationInput,
  RemediationProposal,
  RemediationStatus,
} from '@/services/remediationService'

import { ContextPage } from './ContextPage'

vi.mock('@/hooks/useContext', () => ({ useContextDocument: vi.fn() }))

vi.mock('@/hooks/useStrategies', () => ({ useGenerateStrategies: vi.fn() }))

vi.mock('@/hooks/useEvaluations', () => ({ useEvaluateStrategies: vi.fn() }))

vi.mock('@/hooks/useRankings', () => ({ useRankStrategies: vi.fn() }))

vi.mock('@/hooks/useRemediations', () => ({
  useGenerateRemediation: vi.fn(),
  useRemediations: vi.fn(),
  useUpdateRemediationStatus: vi.fn(),
}))

vi.mock('@/hooks/useMeasurements', () => ({ useCreateMeasurement: vi.fn() }))

vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))

const mockedUseContext = vi.mocked(useContextDocument)
const mockedUseGenerate = vi.mocked(useGenerateStrategies)
const mockedUseEvaluate = vi.mocked(useEvaluateStrategies)
const mockedUseRank = vi.mocked(useRankStrategies)
const mockedUseGenerateRemediation = vi.mocked(useGenerateRemediation)
const mockedUseRemediations = vi.mocked(useRemediations)
const mockedUseUpdateRemediationStatus = vi.mocked(useUpdateRemediationStatus)
const mockedUseCreateMeasurement = vi.mocked(useCreateMeasurement)
const mockedUseAuth = vi.mocked(useAuth)

const CONTEXT = {
  contextVersion: '1.0',
  project: {
    projectId: 'p-1',
    name: 'Homepage',
    description: 'Our main site',
    websiteUrl: 'https://example.com',
    status: 'SCANNED',
  },
  scan: {
    scanId: 's-1',
    projectId: 'p-1',
    scannerType: 'AXE',
    status: 'COMPLETED',
    scannerName: 'axe-core',
    scannerVersion: '4.10.2',
    wcagVersion: '2.2',
    scanUrl: 'https://example.com',
    scanDepth: 1,
    pagesScanned: 1,
    startedAt: '2026-08-14T10:00:00Z',
    completedAt: '2026-08-14T10:00:05Z',
    durationMs: 4800,
    totalDomElements: 40,
    testedElements: 12,
    accessibilityScore: 94,
    totalIssues: 1,
    criticalCount: 0,
    seriousCount: 1,
    moderateCount: 0,
    minorCount: 0,
  },
  page: {
    url: 'https://example.com',
    hostname: 'example.com',
    pathname: '/',
    title: '',
    scannedAt: '2026-08-14T10:00:05Z',
    durationMs: 4800,
    scanner: 'axe-core',
    scannerVersion: '4.10.2',
    totalIssues: 1,
    criticalCount: 0,
    seriousCount: 1,
    moderateCount: 0,
    minorCount: 0,
    accessibilityScore: 94,
  },
  issues: [
    {
      issueId: 'i-1',
      scanId: 's-1',
      projectId: 'p-1',
      rule: {
        ruleId: 'color-contrast',
        ruleName: 'Elements must have sufficient color contrast',
        description: 'Ensures contrast meets WCAG 2 AA thresholds',
        help: 'Elements must have sufficient color contrast',
        helpUrl: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
        impact: 'SERIOUS',
        tags: ['wcag2aa', 'wcag143'],
        wcag: {
          wcagVersion: '2.2',
          level: 'AA',
          tags: ['wcag2aa', 'wcag143'],
          criteria: ['1.4.3'],
          principle: 'Perceivable',
        },
      },
      impact: 'SERIOUS',
      wcag: {
        wcagVersion: '2.2',
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
        domPath: '#main > p',
        textContent: 'Low contrast',
        role: null,
        aria: {},
        form: {},
        surroundingHtml: '',
        parentContext: '',
      },
      evidence: {
        failureSummary: 'Fix any of the following: insufficient contrast',
        xpath: '',
        cssPath: '',
        screenshotPath: '',
        affectedNodes: 1,
      },
      scannerName: 'axe-core',
      scannerVersion: '4.10.2',
    },
  ],
  groups: [
    { groupId: 'rule:color-contrast', groupType: 'same_rule', label: 'Color contrast', issueIds: ['i-1'] },
    { groupId: 'wcag:1.4.3', groupType: 'wcag', label: 'WCAG 1.4.3', issueIds: ['i-1'] },
  ],
  generatedAt: '2026-08-14T10:00:06Z',
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/p-1/scans/s-1/context']}>
      <ContextPage />
    </MemoryRouter>,
  )
}

describe('ContextPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))
    mockedUseContext.mockReturnValue({
      data: CONTEXT,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    mockedUseGenerate.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: null,
      mutateAsync: vi.fn(),
    } as never)
    mockedUseEvaluate.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: null,
      mutateAsync: vi.fn(),
    } as never)
    mockedUseRank.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: null,
      mutateAsync: vi.fn(),
    } as never)
  })

  it('renders project, scan and page context', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Scan context' })).toBeInTheDocument()
    expect(screen.getByText('v1.0')).toBeInTheDocument()
    expect(screen.getByText('Homepage')).toBeInTheDocument()
    expect(screen.getByText(/axe-core/)).toBeInTheDocument()
    expect(screen.getByText('example.com')).toBeInTheDocument()
    expect(screen.getByText('94')).toBeInTheDocument()
  })

  it('renders deterministic issue groups', () => {
    renderPage()

    expect(screen.getByText('Color contrast')).toBeInTheDocument()
    expect(screen.getByText('WCAG 1.4.3')).toBeInTheDocument()
    expect(screen.getAllByText('1 issue').length).toBeGreaterThan(0)
  })

  it('renders issue context with WCAG and element evidence as escaped text', () => {
    renderPage()

    expect(screen.getByText('Elements must have sufficient color contrast')).toBeInTheDocument()
    expect(screen.getByText('1.4.3')).toBeInTheDocument()
    expect(screen.getByText('Perceivable')).toBeInTheDocument()
    // HTML evidence is rendered as literal escaped text — never parsed markup.
    expect(screen.getByText('<p class="muted">Low contrast</p>')).toBeInTheDocument()
    expect(screen.getByText(/Fix any of the following/)).toBeInTheDocument()
    // No img/p element was created from the snippet.
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('shows an error state when context is unavailable', () => {
    mockedUseContext.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Context is only available for completed scans.'),
      refetch: vi.fn(),
    } as never)

    renderPage()

    expect(screen.getByText('Context unavailable')).toBeInTheDocument()
    expect(screen.getByText('Context is only available for completed scans.')).toBeInTheDocument()
  })
})

describe('ContextPage strategy generation', () => {
  const GENERATION: StrategyGeneration = {
    metadata: {
      scanId: 's-1',
      targetType: 'issue',
      issueId: 'i-1',
      groupId: null,
      contextVersion: '1.0',
      promptVersion: '1.0',
      provider: 'mock',
      model: 'mock-model',
      temperature: 0.2,
      strategyCount: 3,
      generatedAt: '2026-08-15T09:00:00Z',
    },
    strategies: [
      {
        strategyId: 'native-1',
        strategyIndex: 1,
        issueId: 'i-1',
        groupId: null,
        contextVersion: '1.0',
        strategyType: 'native_html',
        title: 'Fix color-contrast with native semantic HTML',
        summary: 'Use a native element that satisfies the rule.',
        rationale: 'Native semantics are exposed to assistive technology.',
        implementationSteps: ['Locate the element', 'Replace the markup'],
        expectedAccessibilityImpact: 'high',
        wcagAlignment: ['1.4.3'],
        implementationEffort: 'low',
        maintainabilityNotes: 'Low maintenance.',
        compatibilityNotes: 'Broad support.',
        risks: ['Styling changes'],
        assumptions: ['Editable source'],
        confidence: 0.9,
        evidenceReference: 'i-1',
      },
      {
        strategyId: 'structural-2',
        strategyIndex: 2,
        issueId: 'i-1',
        groupId: null,
        contextVersion: '1.0',
        strategyType: 'structural',
        title: 'Restructure the surrounding markup',
        summary: 'Adjust the DOM structure.',
        rationale: 'Fixes every occurrence at once.',
        implementationSteps: ['Find all occurrences', 'Update the shared component'],
        expectedAccessibilityImpact: 'high',
        wcagAlignment: ['1.4.3'],
        implementationEffort: 'medium',
        maintainabilityNotes: 'Shared change.',
        compatibilityNotes: 'Verify layout.',
        risks: ['Affects other pages'],
        assumptions: ['Shared component'],
        confidence: 0.7,
        evidenceReference: 'i-1',
      },
      {
        strategyId: 'aria-3',
        strategyIndex: 3,
        issueId: 'i-1',
        groupId: null,
        contextVersion: '1.0',
        strategyType: 'aria',
        title: 'Apply targeted ARIA only if native HTML cannot be used',
        summary: 'ARIA fallback.',
        rationale: 'Only when native HTML is unsuitable.',
        implementationSteps: ['Confirm native HTML is not viable'],
        expectedAccessibilityImpact: 'medium',
        wcagAlignment: ['1.4.3'],
        implementationEffort: 'medium',
        maintainabilityNotes: '',
        compatibilityNotes: '',
        risks: ['ARIA can mask issues'],
        assumptions: ['DOM cannot be restructured'],
        confidence: 0.5,
        evidenceReference: 'i-1',
      },
    ],
  }

  /**
   * A real stateful stand-in for React Query's useMutation: the outcome is
   * driven by `generationOutcome.current` (set per test), so isPending /
   * isError transitions actually re-render, exactly like the real hook.
   */
  function FakeUseGenerateStrategies() {
    const [isPending, setIsPending] = useState(false)
    const [isError, setIsError] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const [data, setData] = useState<StrategyGeneration | null>(null)

    const mutateAsync = async (input: { issueId?: string; groupId?: string; strategyCount?: number }) => {
      setIsPending(true)
      try {
        const result = await generationOutcome.current(input)
        setIsPending(false)
        setIsError(false)
        setError(null)
        setData(result)
        return result
      } catch (err) {
        setIsPending(false)
        setIsError(true)
        setError(err instanceof Error ? err : new Error(String(err)))
        setData(null)
        throw err
      }
    }

    return { isPending, isError, error, data, mutateAsync } as never
  }

  const generationOutcome = { current: vi.fn() }

  const EVALUATION_BATCH: EvaluationBatch = {
    scanId: 's-1',
    issueId: 'i-1',
    groupId: null,
    contextVersion: '1.0',
    evaluationVersion: '1.0',
    promptVersion: '1.0',
    provider: 'mock',
    model: 'mock-model',
    evaluations: [
      {
        evaluationId: 'eval-native-1',
        strategyId: 'native-1',
        scanId: 's-1',
        issueId: 'i-1',
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
        strengths: ['Low maintenance burden: the fix lives in plain markup.'],
        weaknesses: ['A native element may change default styling.'],
        rationale: 'Native HTML is the most robust fix for this rule.',
        assumptions: ['The page source is editable.'],
        uncertainties: ['A manual screen-reader check is still required.'],
        evidenceReferences: ['i-1'],
        evaluatorProvider: 'mock',
        evaluatorModel: 'mock-model',
        promptVersion: '1.0',
        evaluatedAt: '2026-08-16T00:00:00Z',
      },
      {
        evaluationId: 'eval-structural-2',
        strategyId: 'structural-2',
        scanId: 's-1',
        issueId: 'i-1',
        groupId: null,
        contextVersion: '1.0',
        evaluationVersion: '1.0',
        accessibilityImpactScore: 9,
        standardsComplianceScore: 8,
        contextualSuitabilityScore: 8,
        implementationEffortScore: 5,
        maintainabilityScore: 7,
        compatibilityScore: 8,
        riskScore: 6,
        strengths: ['Fixes every occurrence at once.'],
        weaknesses: ['Shared templates may affect other pages.'],
        rationale: 'Restructuring targets the shared cause of the rule.',
        assumptions: [],
        uncertainties: ['Regression risk to unrelated content.'],
        evidenceReferences: ['i-1'],
        evaluatorProvider: 'mock',
        evaluatorModel: 'mock-model',
        promptVersion: '1.0',
        evaluatedAt: '2026-08-16T00:00:00Z',
      },
      {
        evaluationId: 'eval-aria-3',
        strategyId: 'aria-3',
        scanId: 's-1',
        issueId: 'i-1',
        groupId: null,
        contextVersion: '1.0',
        evaluationVersion: '1.0',
        accessibilityImpactScore: 6,
        standardsComplianceScore: 7,
        contextualSuitabilityScore: 6,
        implementationEffortScore: 5,
        maintainabilityScore: 5,
        compatibilityScore: 6,
        riskScore: 5,
        strengths: ['Works where the DOM cannot be restructured.'],
        weaknesses: ['ARIA does not change behavior.'],
        rationale: 'ARIA is a fallback when native HTML is unsuitable.',
        assumptions: [],
        uncertainties: [],
        evidenceReferences: ['i-1'],
        evaluatorProvider: 'mock',
        evaluatorModel: 'mock-model',
        promptVersion: '1.0',
        evaluatedAt: '2026-08-16T00:00:00Z',
      },
    ],
  }

  /**
   * A real stateful stand-in for the evaluation mutation, mirroring
   * FakeUseGenerateStrategies: isPending/isError transitions re-render.
   */
  function FakeUseEvaluateStrategies() {
    const [isPending, setIsPending] = useState(false)
    const [isError, setIsError] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const [data, setData] = useState<EvaluationBatch | null>(null)

    const mutateAsync = async (input: {
      issueId?: string
      groupId?: string
      strategies: CandidateStrategy[]
    }) => {
      setIsPending(true)
      try {
        const result = await evaluationOutcome.current(input)
        setIsPending(false)
        setIsError(false)
        setError(null)
        setData(result)
        return result
      } catch (err) {
        setIsPending(false)
        setIsError(true)
        setError(err instanceof Error ? err : new Error(String(err)))
        setData(null)
        throw err
      }
    }

    return { isPending, isError, error, data, mutateAsync } as never
  }

  const evaluationOutcome = { current: vi.fn() }

  const RANKING_BATCH: RankingBatch = {
    scanId: 's-1',
    issueId: 'i-1',
    groupId: null,
    contextVersion: '1.0',
    rankingVersion: '1.0',
    rankingMethod: 'contextual',
    weightsUsed: {
      accessibilityImpact: 0.2,
      standardsCompliance: 0.15,
      contextualSuitability: 0.15,
      implementationEffort: 0.15,
      maintainability: 0.1,
      compatibility: 0.1,
      risk: 0.15,
    },
    contextFactors: [
      {
        factor: 'critical_wcag_issue',
        detected: true,
        influence: 0.3,
        affectedDimensions: ['accessibility_impact', 'standards_compliance'],
        explanation: 'The issue has critical or serious impact.',
      },
    ],
    rankedStrategies: [
      {
        strategyId: 'native-1',
        rank: 1,
        weightedScore: 8.6,
        dimensionScores: {
          accessibility_impact: 9,
          standards_compliance: 9,
          contextual_suitability: 8,
          implementation_effort: 8,
          maintainability: 9,
          compatibility: 9,
          risk: 8,
        },
        strengths: ['Low maintenance burden.'],
        weaknesses: ['Native element may change styling.'],
        rankingExplanation: 'Ranked first for strong impact and compliance.',
        confidence: 0.9,
      },
      {
        strategyId: 'structural-2',
        rank: 2,
        weightedScore: 7.4,
        dimensionScores: {
          accessibility_impact: 9,
          standards_compliance: 8,
          contextual_suitability: 8,
          implementation_effort: 5,
          maintainability: 7,
          compatibility: 8,
          risk: 6,
        },
        strengths: ['Fixes every occurrence.'],
        weaknesses: ['Shared templates may affect other pages.'],
        rankingExplanation: 'Ranked second because of higher effort.',
        confidence: 0.7,
      },
      {
        strategyId: 'aria-3',
        rank: 3,
        weightedScore: 6.1,
        dimensionScores: {
          accessibility_impact: 6,
          standards_compliance: 7,
          contextual_suitability: 6,
          implementation_effort: 5,
          maintainability: 5,
          compatibility: 6,
          risk: 5,
        },
        strengths: ['Works without DOM changes.'],
        weaknesses: ['ARIA does not change behavior.'],
        rankingExplanation: 'Ranked last for lower impact.',
        confidence: 0.5,
      },
    ],
    generatedAt: '2026-08-17T00:00:00Z',
  }

  /**
   * A real stateful stand-in for the ranking mutation, mirroring
   * FakeUseGenerateStrategies: isPending/isError transitions re-render
   * and the resolved batch drives the ranking UI.
   */
  function FakeUseRankStrategies() {
    const [isPending, setIsPending] = useState(false)
    const [isError, setIsError] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const [data, setData] = useState<RankingBatch | null>(null)

    const mutateAsync = async (input: {
      issueId?: string
      groupId?: string
      strategies: CandidateStrategy[]
      evaluations: EvaluationBatch['evaluations']
      mode?: 'baseline' | 'contextual'
    }) => {
      setIsPending(true)
      try {
        const result = await rankingOutcome.current(input)
        setIsPending(false)
        setIsError(false)
        setError(null)
        setData(result)
        return result
      } catch (err) {
        setIsPending(false)
        setIsError(true)
        setError(err instanceof Error ? err : new Error(String(err)))
        setData(null)
        throw err
      }
    }

    return { isPending, isError, error, data, mutateAsync } as never
  }

  const rankingOutcome = { current: vi.fn() }

  const PROPOSAL: RemediationProposal = {
    id: 'rem-1',
    scanId: 's-1',
    issueId: 'i-1',
    strategyId: 'native-1',
    rank: 1,
    title: 'Use native HTML to fix the color contrast',
    summary: 'Replace the low-contrast element with a native element that satisfies the rule.',
    rationale: 'Native semantics are exposed to assistive technology and fix the root cause.',
    implementationSteps: ['Open the component in the codebase', 'Swap the muted class for a contrast-safe one'],
    proposedChange: {
      before: '<span class="muted">Create your account</span>',
      after: '<span class="text-foreground">Create your account</span>',
      filePath: 'src/pages/Home.tsx',
      lineNumber: 42,
      explanation: 'Raise contrast so the text meets WCAG 1.4.3.',
    },
    affectedElement: '<span class="muted">Create your account</span>',
    expectedImprovement: 'The color-contrast issue is resolved for this element.',
    risks: ['A visual redesign may affect brand styling'],
    validationSteps: ['Re-run the scan', 'Visually confirm the contrast'],
    provider: 'mock',
    confidence: 0.92,
    status: 'PROPOSED',
    remediationVersion: '1.0',
    createdAt: '2026-08-18T00:00:00Z',
    updatedAt: '2026-08-18T00:00:00Z',
  }

  // Mutable proposal + outcome controllers so sequential status transitions
  // behave like the real backend (each update starts from the current state).
  const remediationState = { current: PROPOSAL }
  const remediationOutcome = { current: vi.fn() }
  const statusUpdateOutcome = { current: vi.fn() }

  /**
   * A real stateful stand-in for the remediation generation mutation,
   * mirroring the generate/evaluate/rank fakes above.
   */
  function FakeUseGenerateRemediation() {
    const [isPending, setIsPending] = useState(false)
    const [isError, setIsError] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const [data, setData] = useState<RemediationProposal | null>(null)

    const mutateAsync = async (input: GenerateRemediationInput) => {
      setIsPending(true)
      try {
        const result = await remediationOutcome.current(input)
        setIsPending(false)
        setIsError(false)
        setError(null)
        setData(result)
        return result
      } catch (err) {
        setIsPending(false)
        setIsError(true)
        setError(err instanceof Error ? err : new Error(String(err)))
        setData(null)
        throw err
      }
    }

    return { isPending, isError, error, data, mutateAsync } as never
  }

  /**
   * A real stateful stand-in for the status update mutation, mirroring the
   * generate/evaluate/rank fakes above. The outcome is driven by
   * `statusUpdateOutcome.current`, which defaults to applying the transition
   * on top of the current `remediationState`.
   */
  function FakeUseUpdateRemediationStatus() {
    const [isPending, setIsPending] = useState(false)
    const [isError, setIsError] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const [data, setData] = useState<RemediationProposal | null>(null)

    const mutateAsync = async (input: { proposalId: string; status: RemediationStatus }) => {
      setIsPending(true)
      try {
        const result = await statusUpdateOutcome.current(input.proposalId, input.status)
        setIsPending(false)
        setIsError(false)
        setError(null)
        setData(result)
        return result
      } catch (err) {
        setIsPending(false)
        setIsError(true)
        setError(err instanceof Error ? err : new Error(String(err)))
        setData(null)
        throw err
      }
    }

    return { isPending, isError, error, data, mutateAsync } as never
  }

  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))
    mockedUseContext.mockReturnValue({
      data: CONTEXT,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    generationOutcome.current = vi.fn().mockResolvedValue(GENERATION)
    mockedUseGenerate.mockImplementation(FakeUseGenerateStrategies)
    evaluationOutcome.current = vi.fn().mockResolvedValue(EVALUATION_BATCH)
    mockedUseEvaluate.mockImplementation(FakeUseEvaluateStrategies)
    rankingOutcome.current = vi.fn().mockResolvedValue(RANKING_BATCH)
    mockedUseRank.mockImplementation(FakeUseRankStrategies)
    remediationState.current = PROPOSAL
    remediationOutcome.current = vi.fn().mockResolvedValue(PROPOSAL)
    mockedUseGenerateRemediation.mockImplementation(FakeUseGenerateRemediation)
    mockedUseRemediations.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    statusUpdateOutcome.current = vi.fn(
      async (_proposalId: string, status: RemediationStatus) => {
        // Mirror the backend transition: copy the current proposal with the
        // requested status applied.
        remediationState.current = {
          ...remediationState.current,
          status,
          updatedAt: '2026-08-18T01:00:00Z',
        }
        return remediationState.current
      },
    )
    mockedUseUpdateRemediationStatus.mockImplementation(FakeUseUpdateRemediationStatus)
    mockedUseCreateMeasurement.mockReturnValue({
      isPending: false,
      isError: false,
      error: null,
      data: null,
      mutateAsync: vi.fn(),
    } as never)
  })

  it('renders the strategy generation section with a target selector', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Generate strategies' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Strategy target' })).toBeInTheDocument()
    expect(screen.getByLabelText('Strategies')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate' })).toBeInTheDocument()
  })

  it('generates and renders candidate strategy cards on success', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))

    expect(generationOutcome.current).toHaveBeenCalledWith(
      expect.objectContaining({ issueId: 'i-1', strategyCount: 3 }),
    )
    expect(await screen.findByText('Fix color-contrast with native semantic HTML')).toBeInTheDocument()
    expect(screen.getByText('Candidate Strategy 1')).toBeInTheDocument()
    expect(screen.getByText('Candidate Strategy 2')).toBeInTheDocument()
    expect(screen.getByText('Candidate Strategy 3')).toBeInTheDocument()
    // Strategy metadata rendered.
    expect(screen.getByText('Native HTML')).toBeInTheDocument()
    expect(screen.getByText('Structural')).toBeInTheDocument()
    expect(screen.getByText('ARIA')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getByText('Locate the element')).toBeInTheDocument()
    // Traceability metadata.
    expect(screen.getByText(/prompt v1.0/)).toBeInTheDocument()
    // Mock provider is clearly labeled.
    expect(screen.getByText(/LLM_API_KEY for the real model/)).toBeInTheDocument()
  })

  it('shows the loading state while generating', () => {
    // A never-resolving generation keeps the mutation pending.
    generationOutcome.current = vi.fn(() => new Promise(() => {}))
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))

    expect(screen.getByRole('button', { name: /Generating/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Generating/ })).toBeDisabled()
  })

  it('shows an error and allows retry', async () => {
    generationOutcome.current = vi
      .fn()
      .mockRejectedValueOnce(new Error('The language model provider timed out.'))
      .mockResolvedValueOnce(GENERATION)
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The language model provider timed out.',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    expect(await screen.findByText('Fix color-contrast with native semantic HTML')).toBeInTheDocument()
  })

  it('never labels a strategy as best or recommended', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))

    await screen.findByText('Candidate Strategy 1')
    expect(
      screen.queryByRole('heading', { name: /best strategy|recommended strategy|optimal strategy/i }),
    ).toBeNull()
    expect(screen.queryByText('Use this strategy')).toBeNull()
  })

  it('evaluates all generated strategies and shows the seven dimensions', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))

    expect(evaluationOutcome.current).toHaveBeenCalledWith(
      expect.objectContaining({
        issueId: 'i-1',
        strategies: expect.arrayContaining([expect.objectContaining({ strategyId: 'native-1' })]),
      }),
    )

    // Each candidate gets its own independent evaluation.
    expect(await screen.findByText('Candidate Strategy 1 · evaluated')).toBeInTheDocument()
    expect(screen.getByText('Candidate Strategy 2 · evaluated')).toBeInTheDocument()
    expect(screen.getByText('Candidate Strategy 3 · evaluated')).toBeInTheDocument()

    // All seven score dimensions are visible.
    for (const label of [
      'Accessibility Impact',
      'Standards Compliance',
      'Contextual Suitability',
      'Implementation Effort',
      'Maintainability',
      'Compatibility',
      'Risk',
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    expect(screen.getAllByText('9/10').length).toBeGreaterThan(0)
    expect(screen.getAllByText('5/10').length).toBeGreaterThan(0)

    // Qualitative reasoning is displayed.
    expect(screen.getByText('Native HTML is the most robust fix for this rule.')).toBeInTheDocument()
    expect(screen.getByText('Low maintenance burden: the fix lives in plain markup.')).toBeInTheDocument()
    expect(screen.getByText('ARIA does not change behavior.')).toBeInTheDocument()

    // Score semantics and traceability metadata are shown.
    expect(screen.getAllByText(/implementation effort 10 = very easy/)).toHaveLength(3)
    expect(screen.getByText(/3 independent evaluations/)).toBeInTheDocument()
    expect(screen.getAllByText(/evaluation v1.0/).length).toBeGreaterThan(0)
  })

  it('shows the loading state while evaluating', async () => {
    evaluationOutcome.current = vi.fn(() => new Promise(() => {}))
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))

    expect(screen.getByRole('button', { name: /Evaluating/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Evaluating/ })).toBeDisabled()
  })

  it('shows an evaluation error and allows retry', async () => {
    evaluationOutcome.current = vi
      .fn()
      .mockRejectedValueOnce(new Error('The evaluation provider timed out.'))
      .mockResolvedValueOnce(EVALUATION_BATCH)
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The evaluation provider timed out.',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))
    expect(await screen.findByText('Candidate Strategy 1 · evaluated')).toBeInTheDocument()
  })

  it('never ranks an evaluated strategy or calls one best', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))
    await screen.findByText('Candidate Strategy 1 · evaluated')

    expect(
      screen.queryByRole('heading', { name: /best strategy|recommended strategy|optimal strategy|winner/i }),
    ).toBeNull()
    expect(screen.queryByText(/rank #1/i)).toBeNull()
    expect(screen.queryByText('Use this strategy')).toBeNull()
    // Evaluations are labeled as independent, never ranked.
    expect(screen.getAllByText('Independent evaluation of this candidate — no ranking, no total score.')).toHaveLength(3)
  })

  async function driveToEvaluations() {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))
    await screen.findByText('Candidate Strategy 1 · evaluated')
  }

  it('ranks strategies contextually and shows the recommended strategy', async () => {
    await driveToEvaluations()

    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))

    expect(await screen.findByText('Recommended Strategy')).toBeInTheDocument()
    expect(screen.getByText('Rank 2')).toBeInTheDocument()
    expect(screen.getByText('Rank 3')).toBeInTheDocument()
    // Medals for the top three ranks.
    expect(screen.getByText('🥇')).toBeInTheDocument()
    expect(screen.getByText('🥈')).toBeInTheDocument()
    expect(screen.getByText('🥉')).toBeInTheDocument()
    // Weighted scores and the weights used are rendered.
    expect(screen.getByText('8.60')).toBeInTheDocument()
    expect(screen.getByText('Weights used')).toBeInTheDocument()
    expect(screen.getByText('0.20')).toBeInTheDocument()
    // Several dimensions share the 0.15 weight, so expect at least one.
    expect(screen.getAllByText('0.15').length).toBeGreaterThan(0)
    // Ranking explanation and context factors are shown.
    expect(screen.getByText(/Ranked first for strong impact/)).toBeInTheDocument()
    expect(screen.getByText(/Context factors detected/)).toBeInTheDocument()
    expect(screen.getByText(/critical wcag issue/)).toBeInTheDocument()
  })

  it('ranks baseline and compares the two orderings', async () => {
    const baselineBatch: RankingBatch = {
      ...RANKING_BATCH,
      rankingMethod: 'baseline',
      weightsUsed: {
        accessibilityImpact: 1 / 7,
        standardsCompliance: 1 / 7,
        contextualSuitability: 1 / 7,
        implementationEffort: 1 / 7,
        maintainability: 1 / 7,
        compatibility: 1 / 7,
        risk: 1 / 7,
      },
      rankedStrategies: [
        RANKING_BATCH.rankedStrategies[1],
        RANKING_BATCH.rankedStrategies[0],
        RANKING_BATCH.rankedStrategies[2],
      ].map((r, index) => ({ ...r, rank: index + 1 })),
    }
    rankingOutcome.current = vi
      .fn()
      .mockResolvedValueOnce(RANKING_BATCH)
      .mockResolvedValueOnce(baselineBatch)

    await driveToEvaluations()

    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))
    await screen.findByText('Recommended Strategy')

    fireEvent.click(screen.getByRole('button', { name: 'Compare with baseline' }))

    expect(await screen.findByText('Baseline vs context-aware comparison')).toBeInTheDocument()
    expect(
      screen.getByText('Context-aware ranking changed the strategy order compared to baseline.'),
    ).toBeInTheDocument()
    // Both orderings are rendered with their weighted scores.
    expect(screen.getByText('contextual ranking')).toBeInTheDocument()
    expect(screen.getByText('baseline ranking')).toBeInTheDocument()
  })

  it('never crashes when numeric ranking fields are missing or null', async () => {
    // Simulate a payload where the backend omitted the implementation-effort
    // weight and a strategy came back without a weighted score or dimension
    // scores. This used to crash the page with
    // "Cannot read properties of undefined (reading 'toFixed')".
    const missing = JSON.parse(JSON.stringify(RANKING_BATCH))
    delete missing.weightsUsed.implementationEffort
    missing.rankedStrategies[0].weightedScore = null
    delete missing.rankedStrategies[1].dimensionScores.implementation_effort
    missing.rankedStrategies[1].confidence = null
    rankingOutcome.current = vi.fn().mockResolvedValue(missing)

    await driveToEvaluations()

    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))

    // The page still renders the full ranking instead of going blank.
    expect(await screen.findByText('Recommended Strategy')).toBeInTheDocument()
    expect(screen.getByText('Rank 2')).toBeInTheDocument()
    expect(screen.getByText('Weights used')).toBeInTheDocument()
    // Missing values render as a dash rather than crashing.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.getByText(/Ranked 3 strategies/)).toBeInTheDocument()
  })

  it('shows a ranking error and allows retry', async () => {
    rankingOutcome.current = vi
      .fn()
      .mockRejectedValueOnce(new Error('The ranking service timed out.'))
      .mockResolvedValueOnce(RANKING_BATCH)

    await driveToEvaluations()

    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The ranking service timed out.')

    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))
    expect(await screen.findByText('Recommended Strategy')).toBeInTheDocument()
  })

  async function driveToProposal() {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }))
    await screen.findByText('Candidate Strategy 1')
    fireEvent.click(screen.getByRole('button', { name: 'Evaluate strategies' }))
    await screen.findByText('Candidate Strategy 1 · evaluated')
    fireEvent.click(screen.getByRole('button', { name: 'Rank strategies' }))
    await screen.findByText('Recommended Strategy')
    fireEvent.click(screen.getByRole('button', { name: 'Generate remediation' }))
    await screen.findByText(PROPOSAL.title)
  }

  it('shows a generated proposal with its status and full review content', async () => {
    await driveToProposal()

    // Status is visible and starts at PROPOSED.
    expect(screen.getByText('PROPOSED')).toBeInTheDocument()
    // Review content is preserved: summary, rationale, steps, before/after, …
    expect(screen.getByText(PROPOSAL.summary)).toBeInTheDocument()
    expect(screen.getByText(PROPOSAL.rationale)).toBeInTheDocument()
    expect(screen.getByText('Open the component in the codebase')).toBeInTheDocument()
    expect(screen.getByText(PROPOSAL.proposedChange.before)).toBeInTheDocument()
    expect(screen.getByText(PROPOSAL.proposedChange.after)).toBeInTheDocument()
    expect(screen.getByText(/Expected improvement:/)).toBeInTheDocument()
    expect(screen.getByText(/92%/)).toBeInTheDocument()
    // PROPOSED offers the review action.
    expect(screen.getByRole('button', { name: 'Mark as Reviewed' })).toBeInTheDocument()
  })

  it('reviews a PROPOSED proposal (PROPOSED → REVIEWED)', async () => {
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))

    expect(statusUpdateOutcome.current).toHaveBeenCalledWith('rem-1', 'REVIEWED')
    expect(await screen.findByText('REVIEWED')).toBeInTheDocument()
    // The review action is replaced by the accept/reject pair.
    expect(screen.queryByRole('button', { name: 'Mark as Reviewed' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it('accepts a reviewed proposal (REVIEWED → ACCEPTED)', async () => {
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))
    await screen.findByText('REVIEWED')
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))

    expect(statusUpdateOutcome.current).toHaveBeenLastCalledWith('rem-1', 'ACCEPTED')
    expect(await screen.findByText('ACCEPTED')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  })

  it('rejects a reviewed proposal (REVIEWED → REJECTED) with no further actions', async () => {
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))
    await screen.findByText('REVIEWED')
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

    expect(statusUpdateOutcome.current).toHaveBeenLastCalledWith('rem-1', 'REJECTED')
    expect(await screen.findByText('REJECTED')).toBeInTheDocument()
    expect(screen.getByText(/no further action is available/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark as Reviewed' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull()
    // A rejected proposal never unlocks the measurement section.
    expect(screen.queryByLabelText('Follow-up scan ID')).toBeNull()
  })

  it('applies an accepted proposal (ACCEPTED → APPLIED)', async () => {
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))
    await screen.findByText('REVIEWED')
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
    await screen.findByText('ACCEPTED')
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    expect(statusUpdateOutcome.current).toHaveBeenLastCalledWith('rem-1', 'APPLIED')
    expect(await screen.findByText('APPLIED')).toBeInTheDocument()
    expect(screen.getByText(/has been applied/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull()
  })

  it('unlocks the measurement section after ACCEPTED without a refresh', async () => {
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))
    await screen.findByText('REVIEWED')
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))

    // The Module 8 verify/measurement card is gated on ACCEPTED/APPLIED and
    // must appear from local state alone — no page refresh.
    expect(await screen.findByText('ACCEPTED')).toBeInTheDocument()
    expect(screen.getAllByText('Verify remediation').length).toBeGreaterThan(0)
    expect(
      screen.getByText(/Accepted remediation does NOT mean verified improvement/),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Follow-up scan ID')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument()
  })

  it('surfaces a status update error and leaves the proposal reviewable', async () => {
    statusUpdateOutcome.current = vi
      .fn()
      .mockRejectedValueOnce(new Error('The remediation service is unavailable.'))
      .mockImplementationOnce(async (_id: string, status: RemediationStatus) => {
        remediationState.current = {
          ...remediationState.current,
          status,
          updatedAt: '2026-08-18T01:00:00Z',
        }
        return remediationState.current
      })
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The remediation service is unavailable.',
    )
    // The status did not change, so the action remains available for retry.
    expect(screen.getByText('PROPOSED')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark as Reviewed' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))
    expect(await screen.findByText('REVIEWED')).toBeInTheDocument()
  })

  it('disables the status button while the update is pending', async () => {
    statusUpdateOutcome.current = vi.fn(() => new Promise(() => {}))
    await driveToProposal()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as Reviewed' }))

    const reviewButton = screen.getByRole('button', { name: 'Mark as Reviewed' })
    expect(reviewButton).toBeDisabled()
    expect(reviewButton).toHaveAttribute('aria-busy', 'true')
  })
})
