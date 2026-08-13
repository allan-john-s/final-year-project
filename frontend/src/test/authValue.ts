import { vi } from 'vitest'

import type { AuthContextValue, AuthStatus } from '@/contexts/AuthContext'

/** Build a mock auth context value for route-guard tests. */
export function createAuthValue(status: AuthStatus): AuthContextValue {
  return {
    user: null,
    status,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    requestPasswordReset: vi.fn(),
    resetPassword: vi.fn(),
    verifyEmail: vi.fn(),
  }
}
