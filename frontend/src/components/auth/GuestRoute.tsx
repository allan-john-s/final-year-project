import type { ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router-dom'

import { LoadingScreen } from '@/components/auth/LoadingScreen'
import { useAuth } from '@/hooks/useAuth'

interface GuestRouteProps {
  /** Content to render for unauthenticated users. Falls back to `<Outlet />`. */
  children?: ReactNode
}

/**
 * Guards an auth-facing route (login, register, …) from signed-in users.
 *
 * - `loading` → full-screen loading state
 * - `authenticated` → redirect to `/dashboard`
 * - `unauthenticated` → render children (or the nested outlet)
 */
export function GuestRoute({ children }: GuestRouteProps) {
  const { status } = useAuth()

  if (status === 'loading') {
    return <LoadingScreen />
  }

  if (status === 'authenticated') {
    return <Navigate to="/dashboard" replace />
  }

  return children ?? <Outlet />
}
