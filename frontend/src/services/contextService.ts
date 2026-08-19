/**
 * Context service — the single place that talks to the context API.
 *
 * Returns the deterministic, versioned ContextDocument for a completed scan.
 * Follows the scanService/projectService convention: components and hooks
 * depend on this module (never on axios directly) and requests go through
 * `@/lib/api`, which attaches the Supabase bearer token.
 *
 * HTML evidence (`element.html`) is untrusted scanner output — the UI must
 * render it as escaped text (e.g. inside `<pre>`/`<code>`), never as markup.
 */
import { apiClient } from '@/lib/api'

export interface ContextProject {
  projectId: string
  name: string
  description: string
  websiteUrl: string
  status: string
}

export interface ContextScan {
  scanId: string
  projectId: string
  scannerType: string
  status: string
  scannerName: string | null
  scannerVersion: string | null
  wcagVersion: string | null
  scanUrl: string | null
  scanDepth: number
  pagesScanned: number
  startedAt: string | null
  completedAt: string | null
  durationMs: number | null
  totalDomElements: number
  testedElements: number
  accessibilityScore: number | null
  totalIssues: number
  criticalCount: number
  seriousCount: number
  moderateCount: number
  minorCount: number
}

export interface ContextPage {
  url: string
  hostname: string
  pathname: string
  title: string
  scannedAt: string | null
  durationMs: number | null
  scanner: string | null
  scannerVersion: string | null
  totalIssues: number
  criticalCount: number
  seriousCount: number
  moderateCount: number
  minorCount: number
  accessibilityScore: number | null
}

export interface WcagContext {
  wcagVersion: string | null
  level: string | null
  tags: string[]
  criteria: string[]
  principle: string | null
}

export interface RuleContext {
  ruleId: string
  ruleName: string
  description: string
  help: string
  helpUrl: string
  impact: string
  tags: string[]
  wcag: WcagContext
}

export interface ElementContext {
  html: string
  tag: string | null
  attributes: Record<string, string>
  selector: string
  domPath: string
  textContent: string
  role: string | null
  aria: Record<string, string>
  form: Record<string, string>
  surroundingHtml: string
  parentContext: string
}

export interface EvidenceContext {
  failureSummary: string
  xpath: string
  cssPath: string
  screenshotPath: string
  affectedNodes: number
}

export interface ContextIssue {
  issueId: string
  scanId: string
  projectId: string
  rule: RuleContext
  impact: string
  wcag: WcagContext
  element: ElementContext
  evidence: EvidenceContext
  scannerName: string
  scannerVersion: string
}

export interface IssueGroup {
  groupId: string
  groupType: string
  label: string
  issueIds: string[]
}

export interface ContextDocument {
  contextVersion: string
  project: ContextProject
  scan: ContextScan
  page: ContextPage
  issues: ContextIssue[]
  groups: IssueGroup[]
  generatedAt: string
}

interface WcagRow {
  wcag_version: string | null
  level: string | null
  tags: string[]
  criteria: string[]
  principle: string | null
}

interface RuleRow {
  rule_id: string
  rule_name: string
  description: string
  help: string
  help_url: string
  impact: string
  tags: string[]
  wcag: WcagRow
}

interface ElementRow {
  html: string
  tag: string | null
  attributes: Record<string, string>
  selector: string
  dom_path: string
  text_content: string
  role: string | null
  aria: Record<string, string>
  form: Record<string, string>
  surrounding_html: string
  parent_context: string
}

interface EvidenceRow {
  failure_summary: string
  xpath: string
  css_path: string
  screenshot_path: string
  affected_nodes: number
}

interface IssueRow {
  issue_id: string
  scan_id: string
  project_id: string
  rule: RuleRow
  impact: string
  wcag: WcagRow
  element: ElementRow
  evidence: EvidenceRow
  scanner_name: string
  scanner_version: string
}

interface GroupRow {
  group_id: string
  group_type: string
  label: string
  issue_ids: string[]
}

interface ScanRow {
  scan_id: string
  project_id: string
  scanner_type: string
  status: string
  scanner_name: string | null
  scanner_version: string | null
  wcag_version: string | null
  scan_url: string | null
  scan_depth: number
  pages_scanned: number
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  total_dom_elements: number
  tested_elements: number
  accessibility_score: number | null
  total_issues: number
  critical_count: number
  serious_count: number
  moderate_count: number
  minor_count: number
}

interface PageRow {
  url: string
  hostname: string
  pathname: string
  title: string
  scanned_at: string | null
  duration_ms: number | null
  scanner: string | null
  scanner_version: string | null
  total_issues: number
  critical_count: number
  serious_count: number
  moderate_count: number
  minor_count: number
  accessibility_score: number | null
}

interface DocumentRow {
  context_version: string
  project: {
    project_id: string
    name: string
    description: string
    website_url: string
    status: string
  }
  scan: ScanRow
  page: PageRow
  issues: IssueRow[]
  groups: GroupRow[]
  generated_at: string
}

function mapWcag(row: WcagRow): WcagContext {
  return {
    wcagVersion: row.wcag_version,
    level: row.level,
    tags: row.tags,
    criteria: row.criteria,
    principle: row.principle,
  }
}

function mapElement(row: ElementRow): ElementContext {
  return {
    html: row.html,
    tag: row.tag,
    attributes: row.attributes,
    selector: row.selector,
    domPath: row.dom_path,
    textContent: row.text_content,
    role: row.role,
    aria: row.aria,
    form: row.form,
    surroundingHtml: row.surrounding_html,
    parentContext: row.parent_context,
  }
}

function mapIssue(row: IssueRow): ContextIssue {
  return {
    issueId: row.issue_id,
    scanId: row.scan_id,
    projectId: row.project_id,
    rule: {
      ruleId: row.rule.rule_id,
      ruleName: row.rule.rule_name,
      description: row.rule.description,
      help: row.rule.help,
      helpUrl: row.rule.help_url,
      impact: row.rule.impact,
      tags: row.rule.tags,
      wcag: mapWcag(row.rule.wcag),
    },
    impact: row.impact,
    wcag: mapWcag(row.wcag),
    element: mapElement(row.element),
    evidence: {
      failureSummary: row.evidence.failure_summary,
      xpath: row.evidence.xpath,
      cssPath: row.evidence.css_path,
      screenshotPath: row.evidence.screenshot_path,
      affectedNodes: row.evidence.affected_nodes,
    },
    scannerName: row.scanner_name,
    scannerVersion: row.scanner_version,
  }
}

class ContextService {
  async getContext(scanId: string): Promise<ContextDocument> {
    const { data } = await apiClient.get<DocumentRow>(`/api/v1/scans/${scanId}/context`)
    return {
      contextVersion: data.context_version,
      project: {
        projectId: data.project.project_id,
        name: data.project.name,
        description: data.project.description,
        websiteUrl: data.project.website_url,
        status: data.project.status,
      },
      scan: {
        scanId: data.scan.scan_id,
        projectId: data.scan.project_id,
        scannerType: data.scan.scanner_type,
        status: data.scan.status,
        scannerName: data.scan.scanner_name,
        scannerVersion: data.scan.scanner_version,
        wcagVersion: data.scan.wcag_version,
        scanUrl: data.scan.scan_url,
        scanDepth: data.scan.scan_depth,
        pagesScanned: data.scan.pages_scanned,
        startedAt: data.scan.started_at,
        completedAt: data.scan.completed_at,
        durationMs: data.scan.duration_ms,
        totalDomElements: data.scan.total_dom_elements,
        testedElements: data.scan.tested_elements,
        accessibilityScore: data.scan.accessibility_score,
        totalIssues: data.scan.total_issues,
        criticalCount: data.scan.critical_count,
        seriousCount: data.scan.serious_count,
        moderateCount: data.scan.moderate_count,
        minorCount: data.scan.minor_count,
      },
      page: {
        url: data.page.url,
        hostname: data.page.hostname,
        pathname: data.page.pathname,
        title: data.page.title,
        scannedAt: data.page.scanned_at,
        durationMs: data.page.duration_ms,
        scanner: data.page.scanner,
        scannerVersion: data.page.scanner_version,
        totalIssues: data.page.total_issues,
        criticalCount: data.page.critical_count,
        seriousCount: data.page.serious_count,
        moderateCount: data.page.moderate_count,
        minorCount: data.page.minor_count,
        accessibilityScore: data.page.accessibility_score,
      },
      issues: data.issues.map(mapIssue),
      groups: data.groups.map((row) => ({
        groupId: row.group_id,
        groupType: row.group_type,
        label: row.label,
        issueIds: row.issue_ids,
      })),
      generatedAt: data.generated_at,
    }
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const contextService = new ContextService()
