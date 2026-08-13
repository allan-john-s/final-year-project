import { ArrowRight, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { AppHeader } from '@/components/layout/AppHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'

/**
 * Signed-in landing page.
 *
 * The real workspace (projects, scans, issues) is reached from the header
 * navigation; later modules replace the placeholder content below.
 */
export function DashboardPage() {
  const { user } = useAuth()

  return (
    <div className="min-h-svh bg-background text-foreground antialiased">
      <AppHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle className="text-xl">You are signed in</CardTitle>
              <ShieldCheck className="size-5 text-emerald-600" aria-hidden="true" />
            </div>
            <CardDescription>
              Welcome back. Manage the websites you want to analyze for accessibility.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Email</dt>
                <dd className="font-medium">{user?.email ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Display name</dt>
                <dd className="font-medium">{user?.displayName ?? '—'}</dd>
              </div>
            </dl>
            {user?.emailVerified ? <Badge>Email verified</Badge> : null}

            <div className="flex items-center gap-3 rounded-lg border bg-accent/40 p-4">
              <div className="flex-1">
                <p className="text-sm font-medium">Start a project</p>
                <p className="text-sm text-muted-foreground">
                  Add a website to begin accessibility analysis.
                </p>
              </div>
              <Button asChild>
                <Link to="/projects">
                  Go to projects
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
