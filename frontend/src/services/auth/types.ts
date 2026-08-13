/**
 * Authentication service contracts.
 *
 * Everything that needs authentication (context, hooks, pages) depends on
 * `AuthService` — never on a concrete provider. Future providers
 * (Supabase, Firebase, Auth0, custom JWT) only need to implement this
 * interface; no other code changes.
 */

export interface AuthUser {
  id: string
  email: string
  displayName: string | null
  emailVerified: boolean
}

export interface SignInInput {
  email: string
  password: string
}

export interface SignUpInput {
  email: string
  password: string
  displayName?: string
}

export interface ResetPasswordInput {
  token: string
  newPassword: string
}

export interface AuthResult {
  user: AuthUser
}

/** The single seam between the app and any identity provider. */
export interface AuthService {
  /** Resolve the current session, or `null` when unauthenticated. */
  getCurrentUser(): Promise<AuthUser | null>
  signIn(input: SignInInput): Promise<AuthResult>
  signUp(input: SignUpInput): Promise<AuthResult>
  signOut(): Promise<void>
  requestPasswordReset(email: string): Promise<void>
  resetPassword(input: ResetPasswordInput): Promise<void>
  verifyEmail(token: string): Promise<void>

  /**
   * Optional session-lifecycle hooks. Providers that manage their own
   * persisted sessions (e.g. Supabase) implement these so the context can
   * restore a session on boot and react to auth events (sign in/out, token
   * refresh, cross-tab). Stateless providers omit them; `AuthContext` falls
   * back to `getCurrentUser()` in that case.
   */
  restoreSession?(): Promise<AuthUser | null>
  onAuthStateChange?(listener: (user: AuthUser | null) => void): () => void
}
