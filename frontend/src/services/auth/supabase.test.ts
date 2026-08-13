import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'

import { AuthConfigurationError, AuthEmailVerificationRequiredError, AuthError } from './errors'
import { SupabaseAuthService } from './supabase'

const USER = {
  id: 'user-1',
  email: 'dev@example.com',
  email_confirmed_at: '2026-01-01T00:00:00Z',
  user_metadata: { display_name: 'Ada' },
}

function makeAuthMock() {
  const listeners: Array<(event: unknown, session: unknown) => void> = []
  return {
    auth: {
      getUser: vi.fn(async () => ({ data: { user: USER }, error: null })),
      getSession: vi.fn(async () => ({ data: { session: { user: USER } }, error: null })),
      signInWithPassword: vi.fn(async () => ({ data: { user: USER }, error: null })),
      signUp: vi.fn(async () => ({ data: { user: USER, session: { user: USER } }, error: null })),
      signOut: vi.fn(async () => ({ error: null })),
      resetPasswordForEmail: vi.fn(async () => ({ error: null })),
      verifyOtp: vi.fn(async () => ({ error: null })),
      updateUser: vi.fn(async () => ({ data: { user: USER }, error: null })),
      onAuthStateChange: vi.fn((callback: (event: unknown, session: unknown) => void) => {
        listeners.push(callback)
        return {
          data: {
            subscription: {
              unsubscribe: () => {
                const index = listeners.indexOf(callback)
                if (index >= 0) listeners.splice(index, 1)
              },
            },
          },
        }
      }),
    },
    _listeners: listeners,
  }
}

function makeService(overrides: Record<string, unknown> = {}) {
  const mock = makeAuthMock()
  const auth = mock.auth as Record<string, unknown>
  for (const [key, value] of Object.entries(overrides)) {
    auth[key] = value
  }
  return {
    service: new SupabaseAuthService(mock as unknown as SupabaseClient),
    auth: mock.auth,
    listeners: mock._listeners,
  }
}

beforeEach(() => {
  sessionStorage.clear()
})

describe('SupabaseAuthService', () => {
  it('throws AuthConfigurationError when constructed without credentials', () => {
    expect(() => new SupabaseAuthService()).toThrow(AuthConfigurationError)
  })

  it('signs in with email + password and maps the user', async () => {
    const { service, auth } = makeService()
    const result = await service.signIn({ email: 'dev@example.com', password: 'secret1' })

    expect(auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'dev@example.com',
      password: 'secret1',
    })
    expect(result.user).toEqual({
      id: 'user-1',
      email: 'dev@example.com',
      displayName: 'Ada',
      emailVerified: true,
    })
  })

  it('maps provider errors on sign-in', async () => {
    const { service } = makeService({
      signInWithPassword: vi.fn(async () => ({
        data: { user: null, session: null },
        error: { message: 'Invalid login credentials' },
      })),
    })

    await expect(service.signIn({ email: 'dev@example.com', password: 'nope' })).rejects.toThrow(
      AuthError,
    )
  })

  it('signs up and returns the session when no email confirmation is required', async () => {
    const { service, auth } = makeService()
    const result = await service.signUp({
      email: 'dev@example.com',
      password: 'secret1',
      displayName: 'Ada',
    })

    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'dev@example.com',
      password: 'secret1',
      options: { data: { display_name: 'Ada' } },
    })
    expect(result.user.id).toBe('user-1')
  })

  it('requires email verification when sign-up returns no session', async () => {
    const { service } = makeService({
      signUp: vi.fn(async () => ({ data: { user: USER, session: null }, error: null })),
    })

    await expect(service.signUp({ email: 'dev@example.com', password: 'secret1' })).rejects.toThrow(
      AuthEmailVerificationRequiredError,
    )
    expect(sessionStorage.getItem('auth.pending-email')).toBe('dev@example.com')
  })

  it('verifies email using the remembered pending email', async () => {
    const { service, auth } = makeService({
      signUp: vi.fn(async () => ({ data: { user: USER, session: null }, error: null })),
    })

    await service.signUp({ email: 'dev@example.com', password: 'secret1' }).catch(() => undefined)
    await service.verifyEmail('tok-123')

    expect(auth.verifyOtp).toHaveBeenCalledWith({
      email: 'dev@example.com',
      token: 'tok-123',
      type: 'signup',
    })
    expect(sessionStorage.getItem('auth.pending-email')).toBeNull()
  })

  it('fails verifyEmail when no pending email is known', async () => {
    const { service } = makeService()
    await expect(service.verifyEmail('tok-123')).rejects.toThrow(AuthError)
  })

  it('signs out and clears the session', async () => {
    const { service, auth } = makeService()
    await expect(service.signOut()).resolves.toBeUndefined()
    expect(auth.signOut).toHaveBeenCalledOnce()
  })

  it('requests a password reset and remembers the email', async () => {
    const { service, auth } = makeService()
    await service.requestPasswordReset('dev@example.com')

    expect(auth.resetPasswordForEmail).toHaveBeenCalledWith('dev@example.com')
    expect(sessionStorage.getItem('auth.pending-email')).toBe('dev@example.com')
  })

  it('resets the password via a recovery token', async () => {
    const { service, auth } = makeService()
    await service.requestPasswordReset('dev@example.com')
    await service.resetPassword({ token: 'tok-456', newPassword: 'newsecret1' })

    expect(auth.verifyOtp).toHaveBeenCalledWith({
      email: 'dev@example.com',
      token: 'tok-456',
      type: 'recovery',
    })
    expect(auth.updateUser).toHaveBeenCalledWith({ password: 'newsecret1' })
  })

  it('resets the password from an existing magic-link session without a token', async () => {
    const { service, auth } = makeService()
    await service.resetPassword({ token: '', newPassword: 'newsecret1' })
    expect(auth.updateUser).toHaveBeenCalledWith({ password: 'newsecret1' })
    expect(auth.verifyOtp).not.toHaveBeenCalled()
  })

  it('rejects reset without a token and without a session', async () => {
    const { service } = makeService({
      getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    })
    await expect(service.resetPassword({ token: '', newPassword: 'newsecret1' })).rejects.toThrow(
      AuthError,
    )
  })

  it('restores a persisted session', async () => {
    const { service } = makeService()
    const user = await service.restoreSession()
    expect(user?.id).toBe('user-1')
  })

  it('restores no user when no session is persisted', async () => {
    const { service } = makeService({
      getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    })
    await expect(service.restoreSession()).resolves.toBeNull()
  })

  it('resolves the current user via getUser', async () => {
    const { service, auth } = makeService()
    const user = await service.getCurrentUser()
    expect(user?.email).toBe('dev@example.com')
    expect(auth.getUser).toHaveBeenCalledOnce()
  })

  it('notifies listeners on auth state changes and unsubscribes', async () => {
    const { service, listeners, auth } = makeService()
    const listener = vi.fn()

    const unsubscribe = service.onAuthStateChange(listener)
    expect(auth.onAuthStateChange).toHaveBeenCalledOnce()

    listeners[0]?.('SIGNED_IN', { user: USER })
    expect(listener).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: 'user-1', displayName: 'Ada' }),
    )

    // Auto token refresh surfaces as a new session on the same listener.
    listeners[0]?.('TOKEN_REFRESHED', { user: USER })
    expect(listener).toHaveBeenCalledTimes(2)

    listeners[0]?.('SIGNED_OUT', null)
    expect(listener).toHaveBeenLastCalledWith(null)

    unsubscribe()
    listeners.forEach((callback) => callback('SIGNED_IN', { user: USER }))
    expect(listener).toHaveBeenCalledTimes(3)
  })
})
