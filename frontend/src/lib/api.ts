/**
 * Backend API client.
 *
 * A single axios instance pointing at `VITE_API_URL` (defaults to
 * `http://localhost:8000`). Every request is stamped with the current Supabase
 * access token as a Bearer credential — the backend verifies it via JWKS and
 * derives the authenticated user (and project ownership) from it.
 *
 * Errors are normalized into `ApiError` so callers never need to inspect raw
 * axios responses: the backend's `{code, message}` envelope, FastAPI 422
 * validation details, and network failures all map to a single shape.
 */
import axios, { AxiosError, AxiosHeaders, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

import { getSupabaseClient } from '@/lib/supabase'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(message: string, status = 0, code = 'api_error') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const DEFAULT_API_URL = 'http://localhost:8000'

/** Resolve the current Supabase access token, or `null` when unavailable. */
export async function getAccessToken(): Promise<string | null> {
  try {
    const { data, error } = await getSupabaseClient().auth.getSession()
    if (error) return null
    return data.session?.access_token ?? null
  } catch {
    // Supabase not configured (e.g. test env) — requests proceed without a token.
    return null
  }
}

interface ErrorEnvelope {
  code?: unknown
  message?: unknown
}

interface ValidationDetail {
  msg?: unknown
}

function detailMessages(data: unknown): string[] {
  // FastAPI 422 bodies look like `{ detail: [{ msg, loc, ... }, ...] }`.
  const detail =
    data && typeof data === 'object' && Array.isArray((data as { detail?: unknown }).detail)
      ? (data as { detail: unknown[] }).detail
      : []
  return detail
    .filter((item): item is ValidationDetail => typeof item === 'object' && item !== null)
    .map((item) => (typeof item.msg === 'string' ? item.msg : ''))
    .filter(Boolean)
}

/** Map any axios failure onto the shared `ApiError` shape. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error

  const axiosError = error as AxiosError<ErrorEnvelope | unknown[] | undefined>
  const status = axiosError.response?.status ?? 0
  const data = axiosError.response?.data

  if (data && typeof data === 'object' && 'message' in data) {
    const envelope = data as ErrorEnvelope
    const message = typeof envelope.message === 'string' ? envelope.message : 'Request failed.'
    const code = typeof envelope.code === 'string' ? envelope.code : 'api_error'
    return new ApiError(message, status, code)
  }

  if (status === 422) {
    const messages = detailMessages(data)
    return new ApiError(
      messages.length > 0 ? messages.join(' ') : 'The submitted data is invalid.',
      status,
      'validation_error',
    )
  }

  if (axiosError.code === 'ERR_NETWORK' || status === 0) {
    return new ApiError(
      'Cannot reach the API server. Is the backend running?',
      0,
      'network_error',
    )
  }

  return new ApiError(axiosError.message || 'Request failed.', status)
}

/** Create a configured axios instance. Injectable token provider for tests. */
export function createApiClient(
  getToken: () => Promise<string | null> = getAccessToken,
): AxiosInstance {
  const client = axios.create({ baseURL: (import.meta.env.VITE_API_URL as string | undefined) ?? DEFAULT_API_URL })

  client.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
    const token = await getToken()
    if (token) {
      config.headers = config.headers ?? new AxiosHeaders()
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    return config
  })

  client.interceptors.response.use((response) => response, (error: unknown) => Promise.reject(toApiError(error)))

  return client
}

/** The shared client used across the app. */
export const apiClient = createApiClient()
