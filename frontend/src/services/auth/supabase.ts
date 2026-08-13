/**
 * Supabase-backed implementation of the auth service.
 *
 * All identity work is delegated to supabase-js — there is no custom
 * authentication logic:
 *
 *   - sign in / sign up       → `signInWithPassword` / `signUp`
 *   - logout                  → `signOut` (revokes the refresh token)
 *   - password reset          → `resetPasswordForEmail` + `verifyOtp('recovery')` + `updateUser`
 *   - email verification      → `verifyOtp('signup')`
 *   - session persistence     → Supabase localStorage store (persistSession)
 *   - auto token refresh      → Supabase `autoRefreshToken` + TOKEN_REFRESHED events
 *
 * No password is ever stored outside Supabase; tokens live in Supabase's own
 * session store and are refreshed automatically by the client.
 *
 * When email confirmation is required, the sign-up email is remembered (in
 * sessionStorage) so the later `verifyEmail` / `resetPassword` calls can
 * complete without asking the user for it again.
 */
import type { Session, SupabaseClient, User } from '@supabase/supabase-js'

import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase'

import { AuthConfigurationError, AuthEmailVerificationRequiredError, AuthError } from './errors'
import type {
  AuthResult,
  AuthService,
  AuthUser,
  ResetPasswordInput,
  SignInInput,
  SignUpInput,
} from './types'

// --- pending-email store -----------------------------------------------------
// Kept in sessionStorage so a page reload between "sign up" and "verify" (or
// "request reset" and "reset") does not lose the email context.

const PENDING_EMAIL_KEY = 'auth.pending-email'

let pendingEmailCache: string | null = null

function rememberEmail(email: string): void {
  pendingEmailCache = email
  sessionStorage.setItem(PENDING_EMAIL_KEY, email)
}

function pendingEmail(): string | null {
  if (pendingEmailCache === null) {
    pendingEmailCache = sessionStorage.getItem(PENDING_EMAIL_KEY)
  }
  return pendingEmailCache
}

function clearPendingEmail(): void {
  pendingEmailCache = null
  sessionStorage.removeItem(PENDING_EMAIL_KEY)
}

// --- mapping helpers ---------------------------------------------------------

function mapAuthError(error: { message: string }): AuthError {
  return new AuthError(error.message || 'Authentication failed.')
}

function toAuthUser(user: User): AuthUser {
  const metadata = user.user_metadata as Record<string, unknown> | undefined
  return {
    id: user.id,
    email: user.email ?? '',
    displayName:
      (metadata?.display_name as string | undefined) ??
      (metadata?.full_name as string | undefined) ??
      null,
    emailVerified: Boolean(user.email_confirmed_at ?? user.confirmed_at),
  }
}

// --- service -----------------------------------------------------------------

export class SupabaseAuthService implements AuthService {
  private readonly client: SupabaseClient

  constructor(client?: SupabaseClient) {
    if (client) {
      this.client = client
      return
    }
    if (!isSupabaseConfigured()) {
      throw new AuthConfigurationError(
        'Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY ' +
          'to your frontend .env file (see .env.example).',
      )
    }
    this.client = getSupabaseClient()
  }

  /** Resolve the current user from the active session (network-verified). */
  async getCurrentUser(): Promise<AuthUser | null> {
    const { data, error } = await this.client.auth.getUser()
    if (error) throw mapAuthError(error)
    return data.user ? toAuthUser(data.user) : null
  }

  /** Restore the persisted session (localStorage) without a network call. */
  async restoreSession(): Promise<AuthUser | null> {
    const { data, error } = await this.client.auth.getSession()
    if (error) throw mapAuthError(error)
    return data.session?.user ? toAuthUser(data.session.user) : null
  }

  /**
   * Subscribe to auth state changes (sign in/out, token refresh, cross-tab
   * sessions, email confirmation). Returns an unsubscribe function.
   */
  onAuthStateChange(listener: (user: AuthUser | null) => void): () => void {
    const { data } = this.client.auth.onAuthStateChange((event, session) => {
      void event
      listener(session?.user ? toAuthUser(session.user) : null)
    })
    return () => data.subscription.unsubscribe()
  }

  async signIn({ email, password }: SignInInput): Promise<AuthResult> {
    const { data, error } = await this.client.auth.signInWithPassword({ email, password })
    if (error) throw mapAuthError(error)
    if (!data.user) {
      throw new AuthError('Sign in succeeded but returned no user.')
    }
    return { user: toAuthUser(data.user) }
  }

  async signUp({ email, password, displayName }: SignUpInput): Promise<AuthResult> {
    const { data, error } = await this.client.auth.signUp({
      email,
      password,
      options: displayName ? { data: { display_name: displayName } } : undefined,
    })
    if (error) throw mapAuthError(error)
    if (!data.session) {
      // Account created but email confirmation is required — no session yet.
      rememberEmail(email)
      throw new AuthEmailVerificationRequiredError()
    }
    if (!data.user) {
      throw new AuthError('Sign up succeeded but returned no user.')
    }
    return { user: toAuthUser(data.user) }
  }

  async signOut(): Promise<void> {
    const { error } = await this.client.auth.signOut()
    if (error) throw mapAuthError(error)
  }

  async requestPasswordReset(email: string): Promise<void> {
    const { error } = await this.client.auth.resetPasswordForEmail(email)
    if (error) throw mapAuthError(error)
    rememberEmail(email)
  }

  async resetPassword({ token, newPassword }: ResetPasswordInput): Promise<void> {
    const session = await this.currentSession()

    if (token) {
      // Token-based reset (typed-in token from the reset email).
      const email = pendingEmail()
      if (!email) {
        throw new AuthError(
          'Missing email context for the reset token. Request a new reset link and try again.',
        )
      }
      const { error: otpError } = await this.client.auth.verifyOtp({
        email,
        token,
        type: 'recovery',
      })
      if (otpError) throw mapAuthError(otpError)
    } else if (!session) {
      // Magic-link flow: a recovery session should already exist.
      throw new AuthError(
        'No reset session or token found. Request a new reset link and try again.',
      )
    }

    const { error } = await this.client.auth.updateUser({ password: newPassword })
    if (error) throw mapAuthError(error)
  }

  async verifyEmail(token: string): Promise<void> {
    const email = pendingEmail()
    if (!email) {
      throw new AuthError(
        'Missing email context for verification. Sign up again or request a new verification email.',
      )
    }
    const { error } = await this.client.auth.verifyOtp({ email, token, type: 'signup' })
    if (error) throw mapAuthError(error)
    clearPendingEmail()
  }

  private async currentSession(): Promise<Session | null> {
    const { data, error } = await this.client.auth.getSession()
    if (error) throw mapAuthError(error)
    return data.session
  }
}
