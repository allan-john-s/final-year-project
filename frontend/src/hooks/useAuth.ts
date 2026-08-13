import { useContext } from 'react'

import { AuthContext, type AuthContextValue } from '@/contexts/AuthContext'

/**
 * Access the auth context.
 *
 * Must be rendered inside an `<AuthProvider>`. Throws otherwise so misuses
 * fail loudly during development.
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an <AuthProvider>.')
  }
  return context
}
