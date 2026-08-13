import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingScreen } from '@/components/auth/LoadingScreen'
import { useAuth } from '@/hooks/useAuth'

interface ProtectedRouteProps {
  /** Content to render for authenticated users. Falls back to `<Outlet />`. */
  children?: ReactNode
}

/**
 * Guards a route behind authentication.
 *
 * - `loading` → full-screen loading state (session restore in progress)
 * - `unauthenticated` → redirect to `/login`, remembering the intended URL
 * - `authenticated` → render children (or the nested outlet)
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <LoadingScreen />
  }

  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return children ?? <Outlet />
}
