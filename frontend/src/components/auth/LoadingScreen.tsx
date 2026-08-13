import { Loader2 } from 'lucide-react'

/** Full-screen loading state used by route guards while auth resolves. */
export function LoadingScreen() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background"
    >
      <Loader2 className="size-8 animate-spin text-primary" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  )
}
