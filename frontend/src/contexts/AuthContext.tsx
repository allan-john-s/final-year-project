import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  createAuthService,
  type AuthResult,
  type AuthService,
  type AuthUser,
  type ResetPasswordInput,
  type SignInInput,
  type SignUpInput,
} from '@/services/auth'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface AuthContextValue {
  user: AuthUser | null
  status: AuthStatus
  signIn(input: SignInInput): Promise<void>
  signUp(input: SignUpInput): Promise<void>
  signOut(): Promise<void>
  requestPasswordReset(email: string): Promise<void>
  resetPassword(input: ResetPasswordInput): Promise<void>
  verifyEmail(token: string): Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

interface AuthProviderProps {
  /**
   * Injectable auth service; defaults to the factory's configured provider
   * (Supabase when configured, placeholder otherwise).
   */
  service?: AuthService
  children: ReactNode
}

export function AuthProvider({ service, children }: AuthProviderProps) {
  const authService = useMemo(() => service ?? createAuthService(), [service])

  const [user, setUser] = useState<AuthUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  useEffect(() => {
    let active = true

    // Restore a persisted session when the provider supports it (Supabase
    // keeps the session in localStorage); otherwise fall back to a fresh
    // `getCurrentUser()` check.
    const restore = (): Promise<AuthUser | null> =>
      authService.restoreSession ? authService.restoreSession() : authService.getCurrentUser()

    restore()
      .then((current) => {
        if (!active) return
        setUser(current)
        setStatus(current ? 'authenticated' : 'unauthenticated')
      })
      .catch(() => {
        if (!active) return
        setStatus('unauthenticated')
      })

    // Keep the session in sync with provider events: sign in/out, token
    // refresh (TOKEN_REFRESHED), email confirmation, cross-tab changes.
    const unsubscribe = authService.onAuthStateChange?.((next) => {
      if (!active) return
      setUser(next)
      setStatus(next ? 'authenticated' : 'unauthenticated')
    })

    return () => {
      active = false
      unsubscribe?.()
    }
  }, [authService])

  const applyResult = useCallback((result: AuthResult) => {
    setUser(result.user)
    setStatus('authenticated')
  }, [])

  const signIn = useCallback(
    async (input: SignInInput) => {
      applyResult(await authService.signIn(input))
    },
    [authService, applyResult],
  )

  const signUp = useCallback(
    async (input: SignUpInput) => {
      applyResult(await authService.signUp(input))
    },
    [authService, applyResult],
  )

  const signOut = useCallback(async () => {
    await authService.signOut()
    setUser(null)
    setStatus('unauthenticated')
  }, [authService])

  const requestPasswordReset = useCallback(
    async (email: string) => {
      await authService.requestPasswordReset(email)
    },
    [authService],
  )

  const resetPassword = useCallback(
    async (input: ResetPasswordInput) => {
      await authService.resetPassword(input)
    },
    [authService],
  )

  const verifyEmail = useCallback(
    async (token: string) => {
      await authService.verifyEmail(token)
    },
    [authService],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      signIn,
      signUp,
      signOut,
      requestPasswordReset,
      resetPassword,
      verifyEmail,
    }),
    [user, status, signIn, signUp, signOut, requestPasswordReset, resetPassword, verifyEmail],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export { AuthContext }
