import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { createAuthValue } from '@/test/authValue'
import { GuestRoute } from './GuestRoute'

vi.mock('@/hooks/useAuth')

const mockedUseAuth = vi.mocked(useAuth)

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderGuest(ui: ReactNode) {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={ui} />
        <Route path="/dashboard" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('GuestRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a loading screen while the auth status is unknown', () => {
    mockedUseAuth.mockReturnValue(createAuthValue('loading'))

    renderGuest(
      <GuestRoute>
        <div>Guest content</div>
      </GuestRoute>,
    )

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('Guest content')).not.toBeInTheDocument()
  })

  it('redirects authenticated users to /dashboard', async () => {
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))

    renderGuest(
      <GuestRoute>
        <div>Guest content</div>
      </GuestRoute>,
    )

    expect(await screen.findByTestId('location')).toHaveTextContent('/dashboard')
  })

  it('renders children for unauthenticated users', () => {
    mockedUseAuth.mockReturnValue(createAuthValue('unauthenticated'))

    renderGuest(
      <GuestRoute>
        <div>Guest content</div>
      </GuestRoute>,
    )

    expect(screen.getByText('Guest content')).toBeInTheDocument()
  })
})
