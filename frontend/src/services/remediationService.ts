/**
 * Remediation service — the single place that talks to the remediation API
 * (Module 7).
 *
 * POST /api/v1/scans/{scanId}/remediation generates a structured, reviewable
 * remediation proposal for the top-ranked strategy. Proposals are retrieved
 * and managed via separate endpoints.
 *
 * Follows the evaluationService convention: components and hooks depend on
 * this module (never axios directly) and requests go through `@/lib/api`,
 * which attaches the Supabase bearer token.
 */
import { apiClient } from '@/lib/api'
import type { CandidateStrategy } from '@/services/strategyService'
import type { StrategyEvaluation } from '@/services/evaluationService'

export type RemediationStatus = 'PROPOSED' | 'REVIEWED' | 'ACCEPTED' | 'REJECTED' | 'APPLIED'

export interface ProposedChange {
  before: string
  after: string
  filePath: string | null
  lineNumber: number | null
  explanation: string
}

export interface RemediationProposal {
  id: string
  scanId: string
  issueId: string
  strategyId: string
  rank: number
  title: string
  summary: string
  rationale: string
  implementationSteps: string[]
  proposedChange: ProposedChange
  affectedElement: string
  expectedImprovement: string
  risks: string[]
  validationSteps: string[]
  provider: string
  confidence: number
  status: RemediationStatus
  remediationVersion: string
  createdAt: string
  updatedAt: string
}

export interface GenerateRemediationInput {
  issueId: string
  strategyId: string
  strategies: CandidateStrategy[]
  evaluations: StrategyEvaluation[]
}

interface ProposedChangeRow {
  before: string
  after: string
  file_path: string | null
  line_number: number | null
  explanation: string
}

interface RemediationProposalRow {
  id: string
  scan_id: string
  issue_id: string
  strategy_id: string
  rank: number
  title: string
  summary: string
  rationale: string
  implementation_steps: string[]
  proposed_change: ProposedChangeRow
  affected_element: string
  expected_improvement: string
  risks: string[]
  validation_steps: string[]
  provider: string
  confidence: number
  status: RemediationStatus
  remediation_version: string
  created_at: string
  updated_at: string
}

function mapProposal(row: RemediationProposalRow): RemediationProposal {
  return {
    id: row.id,
    scanId: row.scan_id,
    issueId: row.issue_id,
    strategyId: row.strategy_id,
    rank: row.rank,
    title: row.title,
    summary: row.summary,
    rationale: row.rationale,
    implementationSteps: row.implementation_steps,
    proposedChange: {
      before: row.proposed_change.before,
      after: row.proposed_change.after,
      filePath: row.proposed_change.file_path,
      lineNumber: row.proposed_change.line_number,
      explanation: row.proposed_change.explanation,
    },
    affectedElement: row.affected_element,
    expectedImprovement: row.expected_improvement,
    risks: row.risks,
    validationSteps: row.validation_steps,
    provider: row.provider,
    confidence: row.confidence,
    status: row.status,
    remediationVersion: row.remediation_version,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
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

class RemediationService {
  /** Generate a remediation proposal for the top-ranked strategy. */
  async generateRemediation(
    scanId: string,
    input: GenerateRemediationInput,
  ): Promise<RemediationProposal> {
    const { data } = await apiClient.post<RemediationProposalRow>(
      `/api/v1/scans/${scanId}/remediation`,
      {
        issue_id: input.issueId,
        strategy_id: input.strategyId,
        strategies: input.strategies.map(strategyToRow),
        evaluations: input.evaluations.map(evaluationToRow),
      },
    )
    return mapProposal(data)
  }

  /** Get a specific remediation proposal by ID. */
  async getRemediation(proposalId: string): Promise<RemediationProposal> {
    const { data } = await apiClient.get<RemediationProposalRow>(
      `/api/v1/remediations/${proposalId}`,
    )
    return mapProposal(data)
  }

  /** List all remediation proposals for a scan. */
  async listRemediations(scanId: string): Promise<RemediationProposal[]> {
    const { data } = await apiClient.get<RemediationProposalRow[]>(
      `/api/v1/scans/${scanId}/remediations`,
    )
    return data.map(mapProposal)
  }

  /** Update a proposal's status. */
  async updateStatus(
    proposalId: string,
    status: RemediationStatus,
  ): Promise<RemediationProposal> {
    const { data } = await apiClient.patch<RemediationProposalRow>(
      `/api/v1/remediations/${proposalId}/status`,
      { status },
    )
    return mapProposal(data)
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const remediationService = new RemediationService()
