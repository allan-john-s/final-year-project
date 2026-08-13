import {
  ArrowRight,
  CheckCircle2,
  Cpu,
  GitBranch,
  ListChecks,
  ScanLine,
  Sparkles,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const pipeline = [
  {
    icon: ScanLine,
    title: 'Detect',
    description: 'axe-core + Lighthouse surface WCAG violations.',
  },
  {
    icon: Cpu,
    title: 'Context',
    description: 'Surrounding DOM, role, and usage context are captured.',
  },
  {
    icon: GitBranch,
    title: 'Strategies',
    description: 'Multiple remediation approaches are generated.',
  },
  {
    icon: ListChecks,
    title: 'Evaluate',
    description: 'Every strategy is scored against multi-criteria rubrics.',
  },
  { icon: Sparkles, title: 'Recommend', description: 'The best strategy is ranked and explained.' },
  {
    icon: CheckCircle2,
    title: 'Re-scan',
    description: 'Improvement is measured after remediation.',
  },
]

export function LandingPage() {
  return (
    <div className="min-h-svh bg-background text-foreground antialiased">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <ScanLine className="size-4" />
            </span>
            a11y-framework
          </div>
          <Badge variant="secondary">Module 0 · Foundation</Badge>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6">
        <section className="py-20 text-center">
          <Badge className="mb-6">Research project · 2026</Badge>
          <h1 className="mx-auto max-w-3xl text-balance text-4xl font-bold tracking-tight sm:text-5xl">
            A Context-Aware Multi-Strategy Framework for AI-Assisted Web Accessibility Remediation
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-muted-foreground">
            Detection is commodity. Decision is the contribution. This framework helps developers
            select the best remediation strategy for every accessibility issue — with evaluation,
            ranking, and explanation.
          </p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <Button>View the pipeline</Button>
            <Button variant="outline">Read the docs</Button>
          </div>
        </section>

        <section className="pb-20">
          <div className="mb-8 flex items-center gap-3">
            <h2 className="text-xl font-semibold tracking-tight">Research pipeline</h2>
            <ArrowRight className="size-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">six modular stages</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pipeline.map(({ icon: Icon, title, description }) => (
              <Card key={title} className="transition-colors hover:border-ring/60">
                <CardHeader>
                  <span className="mb-2 flex size-9 items-center justify-center rounded-md bg-accent text-accent-foreground">
                    <Icon className="size-4" />
                  </span>
                  <CardTitle className="text-base">{title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription>{description}</CardDescription>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6 text-sm text-muted-foreground">
          <span>React · Vite · TypeScript · TailwindCSS · shadcn/ui</span>
          <span>FastAPI · Python 3.12 · Pydantic v2</span>
        </div>
      </footer>
    </div>
  )
}
