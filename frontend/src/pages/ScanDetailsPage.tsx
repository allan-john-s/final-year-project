import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Clock,
  Globe,
  Loader2,
  RefreshCw,
  ScanLine,
  XCircle,
} from 'lucide-react'
import type { ComponentProps } from 'react'
import { Link, useParams } from 'react-router-dom'

import { AppHeader } from '@/components/layout/AppHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useScan, useScanIssues } from '@/hooks/useScans'
import type { Impact, Scan, ScanIssue, ScanStatus } from '@/services/scanService'

type BadgeVariant = ComponentProps<typeof Badge>['variant']

const STATUS_STYLE: Record<ScanStatus, { label: string; variant: BadgeVariant }> = {
  PENDING: { label: 'Pending', variant: 'outline' },
  RUNNING: { label: 'Running', variant: 'secondary' },
  COMPLETED: { label: 'Completed', variant: 'default' },
  FAILED: { label: 'Failed', variant: 'destructive' },
}

const IMPACT_STYLE: Record<Impact, { label: string; variant: BadgeVariant }> = {
  CRITICAL: { label: 'Critical', variant: 'destructive' },
  SERIOUS: { label: 'Serious', variant: 'default' },
  MODERATE: { label: 'Moderate', variant: 'secondary' },
  MINOR: { label: 'Minor', variant: 'outline' },
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function formatMs(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

interface CountItem {
  label: string
  value: number
  variant: BadgeVariant
}

function countItems(scan: Scan): CountItem[] {
  return [
    { label: 'Critical', value: scan.criticalCount, variant: 'destructive' },
    { label: 'Serious', value: scan.seriousCount, variant: 'default' },
    { label: 'Moderate', value: scan.moderateCount, variant: 'secondary' },
    { label: 'Minor', value: scan.minorCount, variant: 'outline' },
  ]
}

function ScanSummaryCard({ scan }: { scan: Scan }) {
  const status = STATUS_STYLE[scan.status]
  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            {scan.status === 'RUNNING' || scan.status === 'PENDING' ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : scan.status === 'COMPLETED' ? (
              <CheckCircle2 className="size-4 text-emerald-600" aria-hidden="true" />
            ) : scan.status === 'FAILED' ? (
              <XCircle className="size-4 text-destructive" aria-hidden="true" />
            ) : null}
            Scan results
          </CardTitle>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
        <CardDescription className="flex items-center gap-1.5">
          <Globe className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">{scan.scanUrl}</span>
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Accessibility score</p>
            <p className="text-4xl font-bold tracking-tight">
              {scan.accessibilityScore === null ? '—' : scan.accessibilityScore}
            </p>
          </div>
          <div className="text-right text-sm text-muted-foreground">
            <p className="flex items-center justify-end gap-1.5">
              <Clock className="size-3.5" aria-hidden="true" />
              {formatMs(scan.durationMs)}
            </p>
            <p>Started {formatDate(scan.startedAt)}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {countItems(scan).map((item) => (
            <Badge key={item.label} variant={item.variant} className="gap-1">
              {item.value} {item.label.toLowerCase()}
            </Badge>
          ))}
          <Badge variant="outline">{scan.totalIssues} total</Badge>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Scanner</dt>
            <dd>
              {scan.scannerName ?? '—'}
              {scan.scannerVersion ? ` v${scan.scannerVersion}` : ''}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">WCAG</dt>
            <dd>{scan.wcagVersion ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Browser</dt>
            <dd>
              {scan.browserName ?? '—'}
              {scan.browserVersion ? ` ${scan.browserVersion}` : ''}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">DOM elements</dt>
            <dd>{scan.totalDomElements}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Elements tested</dt>
            <dd>{scan.testedElements}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Pages scanned</dt>
            <dd>{scan.pagesScanned}</dd>
          </div>
        </dl>

        {scan.status === 'FAILED' && typeof scan.summary?.error === 'string' ? (
          <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{scan.summary.error}</span>
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function IssueCard({ issue }: { issue: ScanIssue }) {
  const impact = IMPACT_STYLE[issue.impact]
  return (
    <Card className="gap-3">
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{issue.ruleName}</CardTitle>
          <Badge variant={impact.variant}>{impact.label}</Badge>
        </div>
        <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <code className="text-xs">{issue.ruleId}</code>
          {issue.wcagLevel ? <span>WCAG {issue.wcagLevel}</span> : null}
          {issue.helpUrl ? (
            <a
              href={issue.helpUrl}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Learn more
            </a>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {issue.elementSelector ? (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">Target:</span>{' '}
            <code>{issue.elementSelector}</code>
          </p>
        ) : null}
        {issue.failureSummary ? (
          <p className="text-sm text-muted-foreground">{issue.failureSummary}</p>
        ) : null}
        {issue.htmlSnippet ? (
          <pre className="max-h-40 overflow-auto rounded-md bg-accent/60 p-3 text-xs text-foreground">
            <code>{issue.htmlSnippet}</code>
          </pre>
        ) : null}
        {issue.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {issue.tags.map((tag) => (
              <Badge key={tag} variant="ghost" className="text-xs">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function ScanDetailsPage() {
  const { projectId, scanId } = useParams<{ projectId: string; scanId: string }>()
  const {
    data: scan,
    isLoading,
    isError,
    error,
    refetch,
  } = useScan(scanId)
  const { data: issues, isLoading: issuesLoading, isError: issuesError } = useScanIssues(scanId)

  if (isLoading) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto flex max-w-4xl flex-col items-center gap-3 px-6 py-24 text-muted-foreground">
          <Loader2 className="size-6 animate-spin" aria-hidden="true" />
          <span role="status" className="text-sm">
            Loading scan…
          </span>
        </main>
      </div>
    )
  }

  if (isError || !scan) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto max-w-4xl px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>Scan unavailable</CardTitle>
              <CardDescription>{errorMessage(error)}</CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button variant="outline" asChild>
                <Link to={`/projects/${projectId ?? ''}`}>
                  <ArrowLeft className="size-4" aria-hidden="true" />
                  Back to project
                </Link>
              </Button>
              <Button variant="outline" onClick={() => void refetch()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Try again
              </Button>
            </CardContent>
          </Card>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-svh bg-background text-foreground antialiased">
      <AppHeader />

      <main className="mx-auto max-w-4xl px-6 py-12">
        <Button variant="ghost" size="sm" asChild className="mb-4 -ml-2">
          <Link to={`/projects/${projectId ?? ''}`}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to project
          </Link>
        </Button>

        <div className="mb-8 flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <ScanLine className="size-6 text-muted-foreground" aria-hidden="true" />
            Accessibility scan
          </h1>
          {scan.status === 'COMPLETED' ? (
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${projectId ?? ''}/scans/${scanId ?? ''}/context`}>
                <BookOpen className="size-4" aria-hidden="true" />
                View Context
              </Link>
            </Button>
          ) : null}
        </div>

        <div className="space-y-6">
          <ScanSummaryCard scan={scan} />

          <section aria-label="Issues found">
            <h2 className="mb-3 text-lg font-semibold tracking-tight">
              Issues ({scan.totalIssues})
            </h2>
            {issuesLoading ? (
              <div
                role="status"
                aria-label="Loading issues"
                className="flex flex-col items-center gap-3 py-12 text-muted-foreground"
              >
                <Loader2 className="size-5 animate-spin" aria-hidden="true" />
                <span className="text-sm">Loading issues…</span>
              </div>
            ) : issuesError ? (
              <Card>
                <CardHeader>
                  <CardTitle>Could not load issues</CardTitle>
                  <CardDescription>{errorMessage(error)}</CardDescription>
                </CardHeader>
              </Card>
            ) : issues && issues.length > 0 ? (
              <div className="space-y-4">
                {issues.map((issue) => (
                  <IssueCard key={issue.id} issue={issue} />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="py-10 text-center text-sm text-muted-foreground">
                  {scan.status === 'COMPLETED'
                    ? 'No accessibility issues were detected on this page.'
                    : 'No issues reported yet.'}
                </CardContent>
              </Card>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
