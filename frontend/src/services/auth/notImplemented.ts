import { AuthNotImplementedError } from './errors'
import type { AuthResult, AuthService, AuthUser } from './types'

/**
 * Placeholder implementation used until a real provider ships.
 *
 * `getCurrentUser` resolves to `null` so the app boots into the
 * unauthenticated state; every mutating operation raises
 * `AuthNotImplementedError` (surfaced as "Authentication is not implemented
 * yet…" in the UI).
 *
 * Parameters are omitted (not named `_x`) because TypeScript lets an
 * implementation declare fewer parameters than its interface — there is
 * nothing to use yet.
 */
export class NotImplementedAuthService implements AuthService {
  async getCurrentUser(): Promise<AuthUser | null> {
    return null
  }

  async signIn(): Promise<AuthResult> {
    throw new AuthNotImplementedError('signIn')
  }

  async signUp(): Promise<AuthResult> {
    throw new AuthNotImplementedError('signUp')
  }

  async signOut(): Promise<void> {
    throw new AuthNotImplementedError('signOut')
  }

  async requestPasswordReset(): Promise<void> {
    throw new AuthNotImplementedError('requestPasswordReset')
  }

  async resetPassword(): Promise<void> {
    throw new AuthNotImplementedError('resetPassword')
  }

  async verifyEmail(): Promise<void> {
    throw new AuthNotImplementedError('verifyEmail')
  }
}
