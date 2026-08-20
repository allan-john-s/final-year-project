/**
 * Measurement service — talks to the measurement API (Module 8).
 *
 * POST /api/v1/remediations/{remediationId}/measure creates a measurement.
 * GET /api/v1/remediations/{remediationId}/measurements lists measurements.
 * GET /api/v1/measurements/{measurementId} retrieves a measurement.
 */
import { apiClient } from '@/lib/api'

export type MeasurementStatus = 'IMPROVED' | 'NO_CHANGE' | 'REGRESSED' | 'COMPLETED'

export interface ImprovementMeasurement {
  id: string
  remediationId: string
  originalScanId: string
  followupScanId: string
  originalAccessibilityScore: number | null
  followupAccessibilityScore: number | null
  scoreDelta: number | null
  scoreImprovementPercentage: number | null
  originalIssueCount: number
  followupIssueCount: number
  issuesResolved: number
  issuesRemaining: number
  newIssuesIntroduced: number
  criticalBefore: number
  criticalAfter: number
  seriousBefore: number
  seriousAfter: number
  moderateBefore: number
  moderateAfter: number
  minorBefore: number
  minorAfter: number
  status: MeasurementStatus
  measurementSummary: string
  measurementVersion: string
  createdAt: string
}

interface MeasurementRow {
  id: string
  remediation_id: string
  original_scan_id: string
  followup_scan_id: string
  original_accessibility_score: number | null
  followup_accessibility_score: number | null
  score_delta: number | null
  score_improvement_percentage: number | null
  original_issue_count: number
  followup_issue_count: number
  issues_resolved: number
  issues_remaining: number
  new_issues_introduced: number
  critical_before: number
  critical_after: number
  serious_before: number
  serious_after: number
  moderate_before: number
  moderate_after: number
  minor_before: number
  minor_after: number
  status: MeasurementStatus
  measurement_summary: string
  measurement_version: string
  created_at: string
}

function mapMeasurement(row: MeasurementRow): ImprovementMeasurement {
  return {
    id: row.id,
    remediationId: row.remediation_id,
    originalScanId: row.original_scan_id,
    followupScanId: row.followup_scan_id,
    originalAccessibilityScore: row.original_accessibility_score,
    followupAccessibilityScore: row.followup_accessibility_score,
    scoreDelta: row.score_delta,
    scoreImprovementPercentage: row.score_improvement_percentage,
    originalIssueCount: row.original_issue_count,
    followupIssueCount: row.followup_issue_count,
    issuesResolved: row.issues_resolved,
    issuesRemaining: row.issues_remaining,
    newIssuesIntroduced: row.new_issues_introduced,
    criticalBefore: row.critical_before,
    criticalAfter: row.critical_after,
    seriousBefore: row.serious_before,
    seriousAfter: row.serious_after,
    moderateBefore: row.moderate_before,
    moderateAfter: row.moderate_after,
    minorBefore: row.minor_before,
    minorAfter: row.minor_after,
    status: row.status,
    measurementSummary: row.measurement_summary,
    measurementVersion: row.measurement_version,
    createdAt: row.created_at,
  }
}

class MeasurementService {
  /** Create a measurement comparing original scan vs follow-up scan. */
  async createMeasurement(
    remediationId: string,
    followupScanId: string,
  ): Promise<ImprovementMeasurement> {
    const { data } = await apiClient.post<MeasurementRow>(
      `/api/v1/remediations/${remediationId}/measure`,
      { followup_scan_id: followupScanId },
    )
    return mapMeasurement(data)
  }

  /** List all measurements for a remediation. */
  async listMeasurements(remediationId: string): Promise<ImprovementMeasurement[]> {
    const { data } = await apiClient.get<MeasurementRow[]>(
      `/api/v1/remediations/${remediationId}/measurements`,
    )
    return data.map(mapMeasurement)
  }

  /** Get a specific measurement by ID. */
  async getMeasurement(measurementId: string): Promise<ImprovementMeasurement> {
    const { data } = await apiClient.get<MeasurementRow>(
      `/api/v1/measurements/${measurementId}`,
    )
    return mapMeasurement(data)
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const measurementService = new MeasurementService()
