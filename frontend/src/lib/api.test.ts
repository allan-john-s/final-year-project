import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'

import { ApiError, toApiError } from './api'

function axiosError(status: number | undefined, data: unknown, code?: string): AxiosError {
  return new AxiosError('Request failed', code, undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data,
  } as never)
}

describe('toApiError', () => {
  it('passes ApiError instances through unchanged', () => {
    const original = new ApiError('boom', 503, 'project_configuration_error')
    expect(toApiError(original)).toBe(original)
  })

  it('maps the backend {code, message} envelope', () => {
    const error = toApiError(
      axiosError(404, { code: 'project_not_found', message: 'Project not found.' }),
    )
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(404)
    expect(error.code).toBe('project_not_found')
    expect(error.message).toBe('Project not found.')
  })

  it('joins FastAPI 422 validation details into a readable message', () => {
    const error = toApiError(
      axiosError(422, {
        detail: [{ msg: 'website_url must start with http:// or https://.', loc: ['body'] }],
      }),
    )
    expect(error.status).toBe(422)
    expect(error.code).toBe('validation_error')
    expect(error.message).toContain('website_url must start with')
  })

  it('maps network failures to a friendly message', () => {
    const error = toApiError(axiosError(undefined, undefined, 'ERR_NETWORK'))
    expect(error.code).toBe('network_error')
    expect(error.message).toContain('Cannot reach the API server')
  })

  it('falls back to the raw axios message for unknown failures', () => {
    const error = toApiError(axiosError(500, undefined))
    expect(error.status).toBe(500)
    expect(error.message).toBe('Request failed')
  })
})
