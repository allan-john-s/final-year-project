import {
  ArrowLeft,
  BookOpen,
  Braces,
  FileCode2,
  Gauge,
  Globe,
  Layers,
  Loader2,
  RefreshCw,
  Scale,
  ScanLine,
  Shield,
  Sparkles,
  Trophy,
  Wand2,
  Zap,
} from 'lucide-react'
import { useState, type ComponentProps } from 'react'
import { Link, useParams } from 'react-router-dom'

import { AppHeader } from '@/components/layout/AppHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { useContextDocument } from '@/hooks/useContext'
import { useEvaluateStrategies } from '@/hooks/useEvaluations'
import { useGenerateStrategies } from '@/hooks/useStrategies'
import { useRankStrategies } from '@/hooks/useRankings'
import type { ContextDocument, ContextIssue, ContextProject, IssueGroup } from '@/services/contextService'
import { EVALUATION_CRITERIA, type EvaluationBatch, type StrategyEvaluation } from '@/services/evaluationService'
import type {
  CandidateStrategy,
  StrategyGeneration,
  StrategyType,
} from '@/services/strategyService'
import type { ContextFactor, RankingBatch, RankedStrategy } from '@/services/rankingService'

type BadgeVariant = ComponentProps<typeof Badge>['variant']

const IMPACT_STYLE: Record<string, { label: string; variant: BadgeVariant }> = {
  CRITICAL: { label: 'Critical', variant: 'destructive' },
  SERIOUS: { label: 'Serious', variant: 'default' },
  MODERATE: { label: 'Moderate', variant: 'secondary' },
  MINOR: { label: 'Minor', variant: 'outline' },
}

const GROUP_TYPE_LABEL: Record<string, string> = {
  same_rule: 'Same rule',
  same_element: 'Same element',
  wcag: 'WCAG criterion',
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function attributesToText(attributes: Record<string, string>): string {
  return Object.entries(attributes)
    .map(([key, value]) => `${key}="${value}"`)
    .join(' ')
}

function ProjectCard({ project }: { project: ContextProject }) {
  return (
    <Card>
      <CardHeader className="gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="size-4 text-muted-foreground" aria-hidden="true" />
          Project
        </CardTitle>
        <CardDescription className="truncate">{project.websiteUrl}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{project.name}</span>
          <Badge variant={project.status === 'SCANNED' ? 'default' : 'outline'}>
            {project.status.replace(/_/g, ' ').toLowerCase()}
          </Badge>
        </div>
        {project.description ? <p className="text-muted-foreground">{project.description}</p> : null}
      </CardContent>
    </Card>
  )
}

function GroupCard({ group }: { group: IssueGroup }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{group.label}</p>
        <p className="truncate text-xs text-muted-foreground">
          {GROUP_TYPE_LABEL[group.groupType] ?? group.groupType} · {group.groupId}
        </p>
      </div>
      <Badge variant="outline">{group.issueIds.length} issue{group.issueIds.length === 1 ? '' : 's'}</Badge>
    </div>
  )
}

function IssueContextCard({ issue }: { issue: ContextIssue }) {
  const impact = IMPACT_STYLE[issue.impact] ?? IMPACT_STYLE.MODERATE
  const attributeText = attributesToText(issue.element.attributes)

  return (
    <Card className="gap-3">
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{issue.rule.ruleName}</CardTitle>
          <Badge variant={impact.variant}>{impact.label}</Badge>
        </div>
        <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <code className="text-xs">{issue.rule.ruleId}</code>
          {issue.wcag.level ? <span>WCAG {issue.wcag.level}</span> : null}
          {issue.wcag.criteria.length > 0 ? <span>{issue.wcag.criteria.join(', ')}</span> : null}
          {issue.wcag.principle ? <span>{issue.wcag.principle}</span> : null}
          {issue.rule.helpUrl ? (
            <a
              href={issue.rule.helpUrl}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Learn more
            </a>
          ) : null}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {issue.evidence.failureSummary ? (
          <p className="text-sm text-muted-foreground">{issue.evidence.failureSummary}</p>
        ) : null}

        <div className="space-y-1.5 text-xs">
          {issue.element.tag ? (
            <p>
              <span className="font-medium text-muted-foreground">Element:</span>{' '}
              <code>{issue.element.tag}</code>
              {attributeText ? (
                <>
                  {' '}
                  <code>{attributeText}</code>
                </>
              ) : null}
            </p>
          ) : null}
          {issue.element.selector ? (
            <p>
              <span className="font-medium text-muted-foreground">Selector:</span>{' '}
              <code>{issue.element.selector}</code>
            </p>
          ) : null}
          {issue.element.domPath ? (
            <p>
              <span className="font-medium text-muted-foreground">DOM path:</span>{' '}
              <code>{issue.element.domPath}</code>
            </p>
          ) : null}
          {issue.element.textContent ? (
            <p>
              <span className="font-medium text-muted-foreground">Text:</span> {issue.element.textContent}
            </p>
          ) : null}
        </div>

        {issue.element.html ? (
          <div className="space-y-1">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <FileCode2 className="size-3.5" aria-hidden="true" />
              HTML evidence
            </p>
            {/*
              SAFE RENDERING: this is raw scanner output from an untrusted
              page. It is rendered as escaped text inside <pre>/<code> (React
              escapes text content by default) — never as executable markup.
            */}
            <pre className="max-h-48 overflow-auto rounded-md bg-accent/60 p-3 text-xs text-foreground">
              <code>{issue.element.html}</code>
            </pre>
          </div>
        ) : null}

        {Object.keys(issue.element.aria).length > 0 ? (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">ARIA:</span> {attributesToText(issue.element.aria)}
          </p>
        ) : null}

        {issue.rule.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {issue.rule.tags.map((tag) => (
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

const STRATEGY_TYPE_LABEL: Record<StrategyType, string> = {
  native_html: 'Native HTML',
  aria: 'ARIA',
  structural: 'Structural',
  content: 'Content',
  behavioral: 'Behavioral',
  visual: 'Visual',
  alternative: 'Alternative',
  other: 'Other',
}

const EFFORT_LABEL: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

const IMPACT_RATING_LABEL: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

function Confidence({ value }: { value: number }) {
  return <span>{Math.round(value * 100)}%</span>
}

function StrategyCard({ strategy }: { strategy: CandidateStrategy }) {
  return (
    <Card className="gap-3">
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Badge variant="secondary" className="mb-2">
              Candidate Strategy {strategy.strategyIndex}
            </Badge>
            <CardTitle className="text-sm leading-snug">{strategy.title}</CardTitle>
          </div>
          <Badge variant="outline" className="shrink-0">
            {STRATEGY_TYPE_LABEL[strategy.strategyType] ?? strategy.strategyType}
          </Badge>
        </div>
        <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span>
            Impact: {IMPACT_RATING_LABEL[strategy.expectedAccessibilityImpact] ?? strategy.expectedAccessibilityImpact}
          </span>
          <span>
            Effort: {EFFORT_LABEL[strategy.implementationEffort] ?? strategy.implementationEffort}
          </span>
          <span>
            Confidence: <Confidence value={strategy.confidence} />
          </span>
          {strategy.wcagAlignment.length > 0 ? (
            <span>WCAG: {strategy.wcagAlignment.join(', ')}</span>
          ) : null}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        {strategy.summary ? <p>{strategy.summary}</p> : null}

        {strategy.rationale ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Why this strategy applies
            </h4>
            <p className="text-muted-foreground">{strategy.rationale}</p>
          </div>
        ) : null}

        {strategy.implementationSteps.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Implementation steps
            </h4>
            <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
              {strategy.implementationSteps.map((step, index) => (
                <li key={`${strategy.strategyId}-step-${index}`}>{step}</li>
              ))}
            </ol>
          </div>
        ) : null}

        {strategy.wcagAlignment.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">WCAG alignment:</span>
            {strategy.wcagAlignment.map((criterion) => (
              <Badge key={criterion} variant="ghost" className="text-xs">
                {criterion}
              </Badge>
            ))}
          </div>
        ) : null}

        {strategy.maintainabilityNotes || strategy.compatibilityNotes ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {strategy.maintainabilityNotes ? (
              <div className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Maintainability
                </h4>
                <p className="text-muted-foreground">{strategy.maintainabilityNotes}</p>
              </div>
            ) : null}
            {strategy.compatibilityNotes ? (
              <div className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Compatibility
                </h4>
                <p className="text-muted-foreground">{strategy.compatibilityNotes}</p>
              </div>
            ) : null}
          </div>
        ) : null}

        {strategy.risks.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Risks</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {strategy.risks.map((risk, index) => (
                <li key={`${strategy.strategyId}-risk-${index}`}>{risk}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {strategy.assumptions.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Assumptions</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {strategy.assumptions.map((assumption, index) => (
                <li key={`${strategy.strategyId}-assumption-${index}`}>{assumption}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="border-t pt-3 text-xs text-muted-foreground">
          Evidence: <code>{strategy.evidenceReference || '—'}</code>
        </p>
      </CardContent>
    </Card>
  )
}

/**
 * One independent 7-dimensional evaluation of a single candidate strategy.
 * Scores are deliberately shown as separate dimensions — Module 5 produces
 * evidence only, so there is no combined total and no ranking.
 */
function ScoreBar({ label, score }: { label: string; score: number }) {
  const color = score >= 8 ? 'bg-emerald-500' : score >= 5 ? 'bg-amber-500' : 'bg-rose-500'
  return (
    <div className="flex items-center gap-3">
      <span className="w-44 shrink-0 text-xs text-muted-foreground">{label}</span>
      <div
        role="progressbar"
        aria-label={`${label} ${score} out of 10`}
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={10}
        className="h-2 flex-1 overflow-hidden rounded-full bg-accent"
      >
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score * 10}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums">{score}/10</span>
    </div>
  )
}

function EvaluationCard({
  evaluation,
  strategy,
}: {
  evaluation: StrategyEvaluation
  strategy: CandidateStrategy
}) {
  return (
    <Card className="gap-3">
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Badge variant="secondary" className="mb-2">
              Candidate Strategy {strategy.strategyIndex} · evaluated
            </Badge>
            <CardTitle className="text-sm leading-snug">{strategy.title}</CardTitle>
          </div>
        </div>
        <CardDescription className="text-xs">
          Independent evaluation of this candidate — no ranking, no total score.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <div className="space-y-2 rounded-lg border p-3">
          {EVALUATION_CRITERIA.map((criterion) => (
            <ScoreBar key={criterion.label} label={criterion.label} score={criterion.score(evaluation)} />
          ))}
          <p className="pt-1 text-xs text-muted-foreground">
            Score semantics: for every dimension higher is better — implementation effort 10 = very
            easy, risk 10 = very low risk.
          </p>
        </div>

        {evaluation.strengths.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Strengths</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {evaluation.strengths.map((item, index) => (
                <li key={`${evaluation.evaluationId}-strength-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {evaluation.weaknesses.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Weaknesses</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {evaluation.weaknesses.map((item, index) => (
                <li key={`${evaluation.evaluationId}-weakness-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {evaluation.rationale ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rationale</h4>
            <p className="text-muted-foreground">{evaluation.rationale}</p>
          </div>
        ) : null}

        {evaluation.assumptions.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Assumptions</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {evaluation.assumptions.map((item, index) => (
                <li key={`${evaluation.evaluationId}-assumption-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {evaluation.uncertainties.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Uncertainties</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {evaluation.uncertainties.map((item, index) => (
                <li key={`${evaluation.evaluationId}-uncertainty-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {evaluation.evidenceReferences.length > 0 ? (
          <p className="border-t pt-3 text-xs text-muted-foreground">
            Evidence:{" "}
            {evaluation.evidenceReferences.map((reference) => (
              <code key={reference} className="mr-2">
                {reference}
              </code>
            ))}
          </p>
        ) : null}

        <p className="border-t pt-3 text-xs text-muted-foreground">
          Evaluated by <code>{evaluation.evaluatorProvider}</code> · model <code>{evaluation.evaluatorModel}</code> ·
          prompt v{evaluation.promptVersion} · evaluation v{evaluation.evaluationVersion} · context v
          {evaluation.contextVersion} · {formatDate(evaluation.evaluatedAt)}
        </p>
      </CardContent>
    </Card>
  )
}

const RANK_MEDAL: Record<number, string> = {
  1: '🥇',
  2: '🥈',
  3: '🥉',
}

const DIMENSION_LABELS: Record<string, string> = {
  accessibility_impact: 'Accessibility Impact',
  standards_compliance: 'Standards Compliance',
  contextual_suitability: 'Contextual Suitability',
  implementation_effort: 'Implementation Effort',
  maintainability: 'Maintainability',
  compatibility: 'Compatibility',
  risk: 'Risk',
}

function ContextFactorList({ factors }: { factors: ContextFactor[] }) {
  const detected = factors.filter((f) => f.detected)
  if (detected.length === 0) return null
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Context factors detected
      </h4>
      <ul className="list-disc space-y-1 pl-5 text-muted-foreground text-xs">
        {detected.map((factor) => (
          <li key={factor.factor}>
            <span className="font-medium">{factor.factor.replace(/_/g, ' ')}</span>: {factor.explanation}
          </li>
        ))}
      </ul>
    </div>
  )
}

function RankedStrategyCard({
  ranked,
  strategy,
  isRecommended,
}: {
  ranked: RankedStrategy
  strategy: CandidateStrategy | undefined
  isRecommended: boolean
}) {
  return (
    <Card className={`gap-3 ${isRecommended ? 'border-primary ring-1 ring-primary/20' : ''}`}>
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xl" aria-hidden="true">{RANK_MEDAL[ranked.rank] ?? `#${ranked.rank}`}</span>
              <Badge variant={isRecommended ? 'default' : 'secondary'}>
                {isRecommended ? 'Recommended Strategy' : `Rank ${ranked.rank}`}
              </Badge>
            </div>
            <CardTitle className="text-sm leading-snug">
              {strategy?.title ?? ranked.strategyId}
            </CardTitle>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold tabular-nums">{ranked.weightedScore.toFixed(2)}</p>
            <p className="text-xs text-muted-foreground">weighted score</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        <div className="space-y-1.5">
          {Object.entries(ranked.dimensionScores).map(([dim, score]) => (
            <ScoreBar key={dim} label={DIMENSION_LABELS[dim] ?? dim} score={score} />
          ))}
        </div>

        {ranked.strengths.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Strengths</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {ranked.strengths.map((item, index) => (
                <li key={`${ranked.strategyId}-str-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {ranked.weaknesses.length > 0 ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Weaknesses</h4>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              {ranked.weaknesses.map((item, index) => (
                <li key={`${ranked.strategyId}-wk-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {ranked.rankingExplanation ? (
          <div className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ranking explanation
            </h4>
            <p className="text-muted-foreground">{ranked.rankingExplanation}</p>
          </div>
        ) : null}

        <p className="border-t pt-3 text-xs text-muted-foreground">
          Confidence: {Math.round(ranked.confidence * 100)}%
        </p>
      </CardContent>
    </Card>
  )
}

function RankingResults({
  ranking,
  strategies,
  comparison,
  onCompare,
  comparePending,
}: {
  ranking: RankingBatch
  strategies: CandidateStrategy[]
  comparison: RankingBatch | null
  onCompare: () => void
  comparePending: boolean
}) {
  const oppositeMode = ranking.rankingMethod === 'contextual' ? 'baseline' : 'contextual'
  const orderChanged = comparison && JSON.stringify(comparison.rankedStrategies.map((r) => r.strategyId)) !== JSON.stringify(ranking.rankedStrategies.map((r) => r.strategyId))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <p className="flex items-center gap-1.5">
          <Trophy className="size-3.5" aria-hidden="true" />
          Ranked {ranking.rankedStrategies.length} strategies · method{' '}
          <code>{ranking.rankingMethod}</code> · context v{ranking.contextVersion}
        </p>
        <Button variant="outline" size="sm" onClick={onCompare} disabled={comparePending}>
          {comparePending ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Shield className="size-3.5" aria-hidden="true" />
          )}
          Compare with {oppositeMode}
        </Button>
      </div>

      <div className="space-y-2 rounded-lg border p-3 text-xs">
        <h4 className="font-semibold uppercase tracking-wide text-muted-foreground">Weights used</h4>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
          {Object.entries(ranking.weightsUsed).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-muted-foreground">{DIMENSION_LABELS[key] ?? key}</span>
              <span className="font-mono tabular-nums">{(value as number).toFixed(2)}</span>
            </div>
          ))}
        </div>
        <p className="pt-1 text-muted-foreground">
          Total: {Object.values(ranking.weightsUsed).reduce((a, b) => a + (b as number), 0).toFixed(2)}
        </p>
      </div>

      <ContextFactorList factors={ranking.contextFactors} />

      <div className="space-y-3">
        {ranking.rankedStrategies.map((ranked) => (
          <RankedStrategyCard
            key={ranked.strategyId}
            ranked={ranked}
            strategy={strategies.find((s) => s.strategyId === ranked.strategyId)}
            isRecommended={ranked.rank === 1}
          />
        ))}
      </div>

      {comparison ? (
        <Card className="gap-3">
          <CardHeader className="gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="size-4 text-muted-foreground" aria-hidden="true" />
              Baseline vs context-aware comparison
            </CardTitle>
            <CardDescription>
              {orderChanged
                ? 'Context-aware ranking changed the strategy order compared to baseline.'
                : 'Context-aware ranking produced the same order as baseline.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {ranking.rankingMethod} ranking
                </h4>
                <ol className="list-decimal space-y-1 pl-5">
                  {ranking.rankedStrategies.map((r) => {
                    const s = strategies.find((st) => st.strategyId === r.strategyId)
                    return (
                      <li key={r.strategyId} className="text-muted-foreground">
                        {s?.title ?? r.strategyId} ({r.weightedScore.toFixed(2)})
                      </li>
                    )
                  })}
                </ol>
              </div>
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {comparison.rankingMethod} ranking
                </h4>
                <ol className="list-decimal space-y-1 pl-5">
                  {comparison.rankedStrategies.map((r) => {
                    const s = strategies.find((st) => st.strategyId === r.strategyId)
                    return (
                      <li key={r.strategyId} className="text-muted-foreground">
                        {s?.title ?? r.strategyId} ({r.weightedScore.toFixed(2)})
                      </li>
                    )
                  })}
                </ol>
              </div>
            </div>
            {orderChanged ? (
              <p className="text-xs text-muted-foreground">
                The contextual factors caused the ranking to change: {oppositeMode} used equal
                weights, while context-aware adjusted weights based on detected factors.
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

interface StrategySectionProps {
  scanId: string
  context: ContextDocument
}

/**
 * Generate 2–5 candidate remediation strategies for a selected issue or
 * group. Candidates are never ranked here — evaluation/ranking is a later
 * module, so every card is labeled "Candidate Strategy N".
 */
function StrategySection({ scanId, context }: StrategySectionProps) {
  const generate = useGenerateStrategies(scanId)
  const evaluate = useEvaluateStrategies(scanId)
  const [targetType, setTargetType] = useState<'issue' | 'group'>('issue')
  const [issueId, setIssueId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [count, setCount] = useState(3)
  const [result, setResult] = useState<StrategyGeneration | null>(null)
  const [batch, setBatch] = useState<EvaluationBatch | null>(null)
  const [ranking, setRanking] = useState<RankingBatch | null>(null)
  const [comparison, setComparison] = useState<RankingBatch | null>(null)
  const [rankingMode, setRankingMode] = useState<'baseline' | 'contextual'>('contextual')
  // The exact target the generated strategies belong to, so evaluation always
  // uses the same target even if the selects change afterwards.
  const [generationTarget, setGenerationTarget] = useState<{ issueId: string; groupId: string } | null>(null)

  // Default selections fall back to the first available target (the select
  // shows the effective value, so no effect-driven setState is needed).
  const effectiveIssueId = issueId || context.issues[0]?.issueId || ''
  const effectiveGroupId = groupId || context.groups[0]?.groupId || ''

  const hasTargets = context.issues.length > 0 && context.groups.length > 0

  async function handleGenerate() {
    if (!hasTargets) return
    try {
      const generation = await generate.mutateAsync({
        issueId: targetType === 'issue' ? effectiveIssueId : undefined,
        groupId: targetType === 'group' ? effectiveGroupId : undefined,
        strategyCount: count,
      })
      setResult(generation)
      setGenerationTarget({
        issueId: targetType === 'issue' ? effectiveIssueId : '',
        groupId: targetType === 'group' ? effectiveGroupId : '',
      })
      setBatch(null)
      setRanking(null)
      setComparison(null)
    } catch {
      // The failure is surfaced through generate.isError below.
    }
  }

  function resetAll() {
    setResult(null)
    setBatch(null)
    setRanking(null)
    setComparison(null)
    setRankingMode('contextual')
    setGenerationTarget(null)
  }

  async function handleEvaluate() {
    if (!result || !generationTarget) return
    try {
      const evaluations = await evaluate.mutateAsync({
        issueId: generationTarget.issueId || undefined,
        groupId: generationTarget.groupId || undefined,
        strategies: result.strategies,
      })
      setBatch(evaluations)
      setRanking(null)
      setComparison(null)
    } catch {
      // The failure is surfaced through evaluate.isError below.
    }
  }

  const rankMutation = useRankStrategies(scanId)

  async function handleRank() {
    if (!result || !batch || !generationTarget) return
    try {
      const rankingResult = await rankMutation.mutateAsync({
        issueId: generationTarget.issueId || undefined,
        groupId: generationTarget.groupId || undefined,
        strategies: result.strategies,
        evaluations: batch.evaluations,
        mode: rankingMode,
      })
      setRanking(rankingResult)
    } catch {
      // The failure is surfaced through rankMutation.isError below.
    }
  }

  async function handleCompare() {
    if (!result || !batch || !generationTarget) return
    try {
      const oppositeMode = rankingMode === 'contextual' ? 'baseline' : 'contextual'
      const compareResult = await rankMutation.mutateAsync({
        issueId: generationTarget.issueId || undefined,
        groupId: generationTarget.groupId || undefined,
        strategies: result.strategies,
        evaluations: batch.evaluations,
        mode: oppositeMode,
      })
      setComparison(compareResult)
    } catch {
      // The failure is surfaced through rankMutation.isError below.
    }
  }

  return (
    <section aria-label="Generate strategies">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold tracking-tight">
        <Wand2 className="size-5 text-muted-foreground" aria-hidden="true" />
        Generate strategies
      </h2>

      <Card className="gap-4">
        <CardHeader className="gap-2">
          <CardTitle className="text-base">Generate candidate strategies</CardTitle>
          <CardDescription>
            Generate 2–5 distinct remediation candidates for one issue or one issue group. These
            are unranked candidates — the framework does not pick a best strategy at this stage.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {!hasTargets ? (
            <p className="text-sm text-muted-foreground">
              This scan has no issues or groups to generate strategies for.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-2">
                  <Label>Target</Label>
                  <div role="radiogroup" aria-label="Strategy target" className="flex gap-2">
                    <label
                      className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                        targetType === 'issue' ? 'border-primary bg-accent' : ''
                      }`}
                    >
                      <input
                        type="radio"
                        name="target-type"
                        value="issue"
                        checked={targetType === 'issue'}
                        onChange={() => {
                          setTargetType('issue')
                          resetAll()
                        }}
                        className="mr-2"
                      />
                      Issue
                    </label>
                    <label
                      className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                        targetType === 'group' ? 'border-primary bg-accent' : ''
                      }`}
                    >
                      <input
                        type="radio"
                        name="target-type"
                        value="group"
                        checked={targetType === 'group'}
                        onChange={() => {
                          setTargetType('group')
                          resetAll()
                        }}
                        className="mr-2"
                      />
                      Group
                    </label>
                  </div>
                </div>

                <div className="min-w-52 flex-1 space-y-2">
                  <Label htmlFor="strategy-target">
                    {targetType === 'issue' ? 'Issue' : 'Group'}
                  </Label>
                  {targetType === 'issue' ? (
                    <select
                      id="strategy-target"
                      value={effectiveIssueId}
                      onChange={(event) => {
                        setIssueId(event.target.value)
                        resetAll()
                      }}
                      className="w-full rounded-md border bg-transparent px-3 py-2 text-sm"
                    >
                      {context.issues.map((issue) => (
                        <option key={issue.issueId} value={issue.issueId}>
                          {issue.rule.ruleId} — {issue.element.selector || issue.rule.ruleName}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <select
                      id="strategy-target"
                      value={effectiveGroupId}
                      onChange={(event) => {
                        setGroupId(event.target.value)
                        resetAll()
                      }}
                      className="w-full rounded-md border bg-transparent px-3 py-2 text-sm"
                    >
                      {context.groups.map((group) => (
                        <option key={group.groupId} value={group.groupId}>
                          {group.label} ({group.issueIds.length} issue{group.issueIds.length === 1 ? '' : 's'})
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="strategy-count">Strategies</Label>
                  <select
                    id="strategy-count"
                    value={count}
                    onChange={(event) => {
                      setCount(Number(event.target.value))
                      resetAll()
                    }}
                    className="w-24 rounded-md border bg-transparent px-3 py-2 text-sm"
                  >
                    {[2, 3, 4, 5].map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </div>

                <Button
                  onClick={() => void handleGenerate()}
                  disabled={generate.isPending}
                  aria-busy={generate.isPending}
                >
                  {generate.isPending ? (
                    <>
                      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      Generating…
                    </>
                  ) : (
                    <>
                      <Sparkles className="size-4" aria-hidden="true" />
                      Generate
                    </>
                  )}
                </Button>
              </div>

              {generate.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  {errorMessage(generate.error)}
                </p>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {result ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p className="flex items-center gap-1.5">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Generated {result.strategies.length} candidate strategies · provider{' '}
              <code>{result.metadata.provider}</code> · model <code>{result.metadata.model}</code> ·
              prompt v{result.metadata.promptVersion} · context v{result.metadata.contextVersion}
            </p>
            {result.metadata.provider === 'mock' ? (
              <p className="italic">
                Deterministic demonstration provider — configure LLM_API_KEY for the real model.
              </p>
            ) : null}
          </div>
          {result.strategies.map((strategy) => (
            <StrategyCard key={strategy.strategyId} strategy={strategy} />
          ))}

          <Card className="gap-4">
            <CardHeader className="gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Gauge className="size-4 text-muted-foreground" aria-hidden="true" />
                Evaluate candidate strategies
              </CardTitle>
              <CardDescription>
                Evaluate each candidate independently across seven dimensions: accessibility impact,
                standards compliance, contextual suitability, implementation effort, maintainability,
                compatibility and risk. Every strategy gets its own evaluation — this stage never
                picks a best or recommended strategy.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!batch ? (
                <Button
                  onClick={() => void handleEvaluate()}
                  disabled={evaluate.isPending}
                  aria-busy={evaluate.isPending}
                >
                  {evaluate.isPending ? (
                    <>
                      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      Evaluating…
                    </>
                  ) : (
                    <>
                      <Scale className="size-4" aria-hidden="true" />
                      Evaluate strategies
                    </>
                  )}
                </Button>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <p className="flex items-center gap-1.5">
                      <Scale className="size-3.5" aria-hidden="true" />
                      {batch.evaluations.length} independent evaluation
                      {batch.evaluations.length === 1 ? '' : 's'} · provider{' '}
                      <code>{batch.provider}</code> · model <code>{batch.model}</code> · evaluation v
                      {batch.evaluationVersion} · context v{batch.contextVersion}
                    </p>
                    <Button variant="outline" size="sm" onClick={() => setBatch(null)}>
                      <RefreshCw className="size-3.5" aria-hidden="true" />
                      Re-evaluate
                    </Button>
                  </div>
                  {batch.evaluations.map((evaluation) => {
                    const strategy = result.strategies.find(
                      (candidate) => candidate.strategyId === evaluation.strategyId,
                    )
                    if (!strategy) return null
                    return (
                      <EvaluationCard
                        key={evaluation.evaluationId}
                        evaluation={evaluation}
                        strategy={strategy}
                      />
                    )
                  })}
                </div>
              )}

              {evaluate.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  {errorMessage(evaluate.error)}
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {batch ? (
        <div className="mt-4 space-y-4">
          <Card className="gap-4">
            <CardHeader className="gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Trophy className="size-4 text-muted-foreground" aria-hidden="true" />
                Rank strategies
              </CardTitle>
              <CardDescription>
                Rank evaluated strategies using transparent, context-aware weighted scoring. Choose
                context-aware or baseline mode, then compare how the rankings differ.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!ranking ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="space-y-2">
                      <Label>Ranking mode</Label>
                      <div role="radiogroup" aria-label="Ranking mode" className="flex gap-2">
                        <label
                          className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                            rankingMode === 'contextual' ? 'border-primary bg-accent' : ''
                          }`}
                        >
                          <input
                            type="radio"
                            name="ranking-mode"
                            value="contextual"
                            checked={rankingMode === 'contextual'}
                            onChange={() => setRankingMode('contextual')}
                            className="mr-2"
                          />
                          Context-aware
                        </label>
                        <label
                          className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                            rankingMode === 'baseline' ? 'border-primary bg-accent' : ''
                          }`}
                        >
                          <input
                            type="radio"
                            name="ranking-mode"
                            value="baseline"
                            checked={rankingMode === 'baseline'}
                            onChange={() => setRankingMode('baseline')}
                            className="mr-2"
                          />
                          Baseline
                        </label>
                      </div>
                    </div>
                    <Button
                      onClick={() => void handleRank()}
                      disabled={rankMutation.isPending}
                      aria-busy={rankMutation.isPending}
                    >
                      {rankMutation.isPending ? (
                        <>
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                          Ranking…
                        </>
                      ) : (
                        <>
                          <Zap className="size-4" aria-hidden="true" />
                          Rank strategies
                        </>
                      )}
                    </Button>
                  </div>
                  {rankMutation.isError ? (
                    <p role="alert" className="text-sm text-destructive">
                      {errorMessage(rankMutation.error)}
                    </p>
                  ) : null}
                </div>
              ) : (
                <RankingResults
                  ranking={ranking}
                  strategies={result?.strategies ?? []}
                  comparison={comparison}
                  onCompare={() => void handleCompare()}
                  comparePending={rankMutation.isPending}
                />
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </section>
  )
}

export function ContextPage() {
  const { projectId, scanId } = useParams<{ projectId: string; scanId: string }>()
  const { data: context, isLoading, isError, error, refetch } = useContextDocument(scanId)

  if (isLoading) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto flex max-w-4xl flex-col items-center gap-3 px-6 py-24 text-muted-foreground">
          <Loader2 className="size-6 animate-spin" aria-hidden="true" />
          <span role="status" className="text-sm">
            Building context…
          </span>
        </main>
      </div>
    )
  }

  if (isError || !context) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto max-w-4xl px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>Context unavailable</CardTitle>
              <CardDescription>{errorMessage(error)}</CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button variant="outline" asChild>
                <Link to={`/projects/${projectId ?? ''}/scans/${scanId ?? ''}`}>
                  <ArrowLeft className="size-4" aria-hidden="true" />
                  Back to scan
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
          <Link to={`/projects/${projectId ?? ''}/scans/${scanId ?? ''}`}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to scan
          </Link>
        </Button>

        <div className="mb-8 flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <BookOpen className="size-6 text-muted-foreground" aria-hidden="true" />
            Scan context
          </h1>
          <Badge variant="secondary">v{context.contextVersion}</Badge>
        </div>

        <div className="space-y-6">
          <div className="grid gap-6 sm:grid-cols-2">
            <ProjectCard project={context.project} />

            <Card>
              <CardHeader className="gap-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ScanLine className="size-4 text-muted-foreground" aria-hidden="true" />
                  Scan
                </CardTitle>
                <CardDescription>Generated {formatDate(context.generatedAt)}</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div>
                  <p className="text-muted-foreground">Scanner</p>
                  <p>
                    {context.scan.scannerName ?? '—'}
                    {context.scan.scannerVersion ? ` v${context.scan.scannerVersion}` : ''}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Type</p>
                  <p>{context.scan.scannerType}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">WCAG</p>
                  <p>{context.scan.wcagVersion ?? '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Duration</p>
                  <p>{context.scan.durationMs !== null ? `${(context.scan.durationMs / 1000).toFixed(1)}s` : '—'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">DOM elements</p>
                  <p>{context.scan.totalDomElements}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Elements tested</p>
                  <p>{context.scan.testedElements}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Started</p>
                  <p>{formatDate(context.scan.startedAt)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Completed</p>
                  <p>{formatDate(context.scan.completedAt)}</p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Globe className="size-4 text-muted-foreground" aria-hidden="true" />
                Page
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              <div className="col-span-2 sm:col-span-3">
                <p className="text-muted-foreground">URL</p>
                <p className="truncate">{context.page.url}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Hostname</p>
                <p>{context.page.hostname || '—'}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Path</p>
                <p>{context.page.pathname || '—'}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Score</p>
                <p className="font-semibold">
                  {context.page.accessibilityScore === null ? '—' : context.page.accessibilityScore}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Critical / serious</p>
                <p>
                  {context.page.criticalCount} / {context.page.seriousCount}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Moderate / minor</p>
                <p>
                  {context.page.moderateCount} / {context.page.minorCount}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Scanned at</p>
                <p>{formatDate(context.page.scannedAt)}</p>
              </div>
            </CardContent>
          </Card>

          <section aria-label="Issue groups">
            <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold tracking-tight">
              <Layers className="size-5 text-muted-foreground" aria-hidden="true" />
              Issue groups ({context.groups.length})
            </h2>
            {context.groups.length > 0 ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {context.groups.map((group) => (
                  <GroupCard key={group.groupId} group={group} />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No issue groups — this scan has no findings.
                </CardContent>
              </Card>
            )}
          </section>

          <section aria-label="Issue context">
            <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold tracking-tight">
              <Braces className="size-5 text-muted-foreground" aria-hidden="true" />
              Issues ({context.issues.length})
            </h2>
            {context.issues.length > 0 ? (
              <div className="space-y-4">
                {context.issues.map((issue) => (
                  <IssueContextCard key={issue.issueId} issue={issue} />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No issues were detected on this page.
                </CardContent>
              </Card>
            )}
          </section>

          <StrategySection scanId={scanId ?? ''} context={context} />
        </div>
      </main>
    </div>
  )
}
