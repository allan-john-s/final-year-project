import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  AuthError,
  AuthNotImplementedError,
  createAuthService,
  NotImplementedAuthService,
  SupabaseAuthService,
} from './index'
import type { AuthService } from './types'

describe('AuthService abstraction', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('exposes a factory whose result satisfies the AuthService interface', () => {
    const service: AuthService = createAuthService()
    expect(service).toBeInstanceOf(NotImplementedAuthService)
  })

  it('returns the Supabase service when credentials are configured', () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv(
      'VITE_SUPABASE_ANON_KEY',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ0ZXN0In0.abc',
    )
    expect(createAuthService()).toBeInstanceOf(SupabaseAuthService)
  })

  it('reports no current user until a provider is connected', async () => {
    const service = createAuthService()
    await expect(service.getCurrentUser()).resolves.toBeNull()
  })

  it('every mutating operation raises AuthNotImplementedError', async () => {
    const service = createAuthService()
    const calls = [
      service.signIn({ email: 'dev@example.com', password: 'secret1' }),
      service.signUp({ email: 'dev@example.com', password: 'secret1', displayName: 'Ada' }),
      service.signOut(),
      service.requestPasswordReset('dev@example.com'),
      service.resetPassword({ token: 'token', newPassword: 'newsecret1' }),
      service.verifyEmail('token'),
    ]

    for (const call of calls) {
      await expect(call).rejects.toBeInstanceOf(AuthNotImplementedError)
    }
  })

  it('AuthNotImplementedError is an AuthError', () => {
    expect(new AuthNotImplementedError('signIn')).toBeInstanceOf(AuthError)
  })
})
