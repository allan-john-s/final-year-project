import { ScanLine } from 'lucide-react'
import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface AuthShellProps {
  title: string
  description: string
  children: ReactNode
}

/** Centered card layout shared by every auth page. */
export function AuthShell({ title, description, children }: AuthShellProps) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-muted/40 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ScanLine className="size-5" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold tracking-tight">a11y-framework</span>
        </div>

        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-xl">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent>{children}</CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">Research project · 2026</p>
      </div>
    </main>
  )
}
