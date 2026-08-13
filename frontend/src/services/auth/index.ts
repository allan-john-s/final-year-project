/**
 * Authentication service layer — public entry point.
 *
 * Import from `@/services/auth`. The factory is the only place that decides
 * which provider backs the app; swapping Supabase → Firebase → Auth0 requires
 * changing exactly this function (and nothing else).
 */
import { isSupabaseConfigured } from '@/lib/supabase'

import { NotImplementedAuthService } from './notImplemented'
import { SupabaseAuthService } from './supabase'
import type { AuthService } from './types'

export {
  AuthConfigurationError,
  AuthEmailVerificationRequiredError,
  AuthError,
  AuthNotImplementedError,
} from './errors'
export { NotImplementedAuthService } from './notImplemented'
export { SupabaseAuthService } from './supabase'
export type {
  AuthResult,
  AuthService,
  AuthUser,
  ResetPasswordInput,
  SignInInput,
  SignUpInput,
} from './types'

/**
 * Create the configured auth service.
 *
 * When `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` are present the app runs
 * on the real Supabase provider; otherwise it falls back to the placeholder
 * so development and tests never require credentials.
 */
export function createAuthService(): AuthService {
  if (isSupabaseConfigured()) {
    return new SupabaseAuthService()
  }
  return new NotImplementedAuthService()
}
