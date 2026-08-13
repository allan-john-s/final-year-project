import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { createAuthValue } from '@/test/authValue'
import { ProtectedRoute } from './ProtectedRoute'

vi.mock('@/hooks/useAuth')

const mockedUseAuth = vi.mocked(useAuth)

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderProtected(ui: ReactNode) {
  return render(
    <MemoryRouter initialEntries={['/protected']}>
      <Routes>
        <Route path="/protected" element={ui} />
        <Route path="/login" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a loading screen while the auth status is unknown', () => {
    mockedUseAuth.mockReturnValue(createAuthValue('loading'))

    renderProtected(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
  })

  it('redirects unauthenticated users to /login', async () => {
    mockedUseAuth.mockReturnValue(createAuthValue('unauthenticated'))

    renderProtected(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    expect(await screen.findByTestId('location')).toHaveTextContent('/login')
  })

  it('renders children for authenticated users', () => {
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))

    renderProtected(
      <ProtectedRoute>
        <div>Protected content</div>
      </ProtectedRoute>,
    )

    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })
})
