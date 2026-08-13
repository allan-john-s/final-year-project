/**
 * Supabase client bootstrap.
 *
 * The client is created lazily from `VITE_SUPABASE_URL` /
 * `VITE_SUPABASE_ANON_KEY` and cached as a singleton. When the environment
 * variables are missing, `isSupabaseConfigured()` is `false` and the auth
 * factory falls back to the placeholder service — so development and the test
 * suite never require Supabase credentials.
 *
 * Session persistence and auto token refresh are Supabase client features:
 * `persistSession` keeps the session in localStorage across reloads,
 * `autoRefreshToken` refreshes it before expiry, and `detectSessionInUrl`
 * handles magic-link / email-confirmation URLs. No custom auth logic here.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

export function isSupabaseConfigured(): boolean {
  return Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY)
}

let client: SupabaseClient | null = null

/**
 * Create (once) and return the Supabase client.
 * @throws {Error} when `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` are missing.
 */
export function getSupabaseClient(): SupabaseClient {
  const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined
  if (!url || !anonKey) {
    throw new Error(
      'Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY ' +
        'to your frontend .env file (see .env.example).',
    )
  }
  if (!client) {
    client = createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  }
  return client
}
