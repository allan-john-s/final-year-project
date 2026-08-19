/**
 * Scan service — the single place that talks to the scans API.
 *
 * Follows the projectService convention: components and hooks depend on this
 * module (never on axios directly) and all requests go through `@/lib/api`,
 * which attaches the Supabase bearer token and normalizes errors.
 *
 * Ownership is derived from the authenticated JWT on the backend — no
 * `user_id` (or `project_id` in the POST body) is ever sent by the client.
 */
import { apiClient } from '@/lib/api'

export type ScanStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
export type ScannerType = 'AXE' | 'LIGHTHOUSE' | 'PA11Y' | 'WAVE' | 'RESEARCH'
export type Impact = 'CRITICAL' | 'SERIOUS' | 'MODERATE' | 'MINOR'
export type WcagLevel = 'A' | 'AA' | 'AAA'

export interface Scan {
  id: string
  projectId: string
  scannerType: ScannerType
  status: ScanStatus
  startedAt: string | null
  completedAt: string | null
  durationMs: number | null
  summary: Record<string, unknown>
  totalIssues: number
  criticalCount: number
  seriousCount: number
  moderateCount: number
  minorCount: number
  accessibilityScore: number | null
  scannerName: string | null
  scannerVersion: string | null
  wcagVersion: string | null
  scanUrl: string | null
  scanDepth: number
  pagesScanned: number
  browserName: string | null
  browserVersion: string | null
  userAgent: string | null
  totalDomElements: number
  testedElements: number
  normalizationDurationMs: number | null
  persistenceDurationMs: number | null
  createdAt: string
}

export interface ScanIssue {
  id: string
  scanId: string
  ruleId: string
  ruleName: string
  description: string
  help: string
  helpUrl: string
  impact: Impact
  wcagLevel: WcagLevel | null
  tags: string[]
  elementSelector: string
  htmlSnippet: string
  failureSummary: string
  xpath: string
  cssPath: string
  domPath: string
  screenshotPath: string
  createdAt: string
}

interface ScanRow {
  id: string
  project_id: string
  scanner_type: ScannerType
  status: ScanStatus
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  summary: Record<string, unknown>
  total_issues: number
  critical_count: number
  serious_count: number
  moderate_count: number
  minor_count: number
  accessibility_score: number | null
  scanner_name: string | null
  scanner_version: string | null
  wcag_version: string | null
  scan_url: string | null
  scan_depth: number
  pages_scanned: number
  browser_name: string | null
  browser_version: string | null
  user_agent: string | null
  total_dom_elements: number
  tested_elements: number
  normalization_duration_ms: number | null
  persistence_duration_ms: number | null
  created_at: string
}

interface IssueRow {
  id: string
  scan_id: string
  rule_id: string
  rule_name: string
  description: string
  help: string
  help_url: string
  impact: Impact
  wcag_level: WcagLevel | null
  tags: string[]
  element_selector: string
  html_snippet: string
  failure_summary: string
  xpath: string
  css_path: string
  dom_path: string
  screenshot_path: string
  created_at: string
}

function mapScan(row: ScanRow): Scan {
  return {
    id: row.id,
    projectId: row.project_id,
    scannerType: row.scanner_type,
    status: row.status,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    durationMs: row.duration_ms,
    summary: row.summary,
    totalIssues: row.total_issues,
    criticalCount: row.critical_count,
    seriousCount: row.serious_count,
    moderateCount: row.moderate_count,
    minorCount: row.minor_count,
    accessibilityScore: row.accessibility_score,
    scannerName: row.scanner_name,
    scannerVersion: row.scanner_version,
    wcagVersion: row.wcag_version,
    scanUrl: row.scan_url,
    scanDepth: row.scan_depth,
    pagesScanned: row.pages_scanned,
    browserName: row.browser_name,
    browserVersion: row.browser_version,
    userAgent: row.user_agent,
    totalDomElements: row.total_dom_elements,
    testedElements: row.tested_elements,
    normalizationDurationMs: row.normalization_duration_ms,
    persistenceDurationMs: row.persistence_duration_ms,
    createdAt: row.created_at,
  }
}

function mapIssue(row: IssueRow): ScanIssue {
  return {
    id: row.id,
    scanId: row.scan_id,
    ruleId: row.rule_id,
    ruleName: row.rule_name,
    description: row.description,
    help: row.help,
    helpUrl: row.help_url,
    impact: row.impact,
    wcagLevel: row.wcag_level,
    tags: row.tags,
    elementSelector: row.element_selector,
    htmlSnippet: row.html_snippet,
    failureSummary: row.failure_summary,
    xpath: row.xpath,
    cssPath: row.css_path,
    domPath: row.dom_path,
    screenshotPath: row.screenshot_path,
    createdAt: row.created_at,
  }
}

class ScanService {
  async startScan(projectId: string, scannerType: ScannerType = 'AXE'): Promise<Scan> {
    const { data } = await apiClient.post<ScanRow>(`/api/v1/projects/${projectId}/scan`, {
      scanner_type: scannerType,
    })
    return mapScan(data)
  }

  async listScans(): Promise<Scan[]> {
    const { data } = await apiClient.get<ScanRow[]>('/api/v1/scans')
    return data.map(mapScan)
  }

  async getScan(id: string): Promise<Scan> {
    const { data } = await apiClient.get<ScanRow>(`/api/v1/scans/${id}`)
    return mapScan(data)
  }

  async listProjectScans(projectId: string): Promise<Scan[]> {
    const { data } = await apiClient.get<ScanRow[]>(`/api/v1/projects/${projectId}/scans`)
    return data.map(mapScan)
  }

  async getIssues(scanId: string): Promise<ScanIssue[]> {
    const { data } = await apiClient.get<IssueRow[]>(`/api/v1/scans/${scanId}/issues`)
    return data.map(mapIssue)
  }

  async deleteScan(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/scans/${id}`)
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const scanService = new ScanService()
