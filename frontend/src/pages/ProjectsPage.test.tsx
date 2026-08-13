import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/hooks/useAuth'
import { useCreateProject, useDeleteProject, useProjects } from '@/hooks/useProjects'
import { createAuthValue } from '@/test/authValue'

import { ProjectsPage } from './ProjectsPage'

vi.mock('@/hooks/useProjects', () => ({
  useProjects: vi.fn(),
  useCreateProject: vi.fn(),
  useDeleteProject: vi.fn(),
  useUpdateProject: vi.fn(),
  projectsKey: ['projects'] as const,
}))

vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }))

const mockedUseProjects = vi.mocked(useProjects)
const mockedUseCreateProject = vi.mocked(useCreateProject)
const mockedUseDeleteProject = vi.mocked(useDeleteProject)
const mockedUseAuth = vi.mocked(useAuth)

const PROJECT = {
  id: 'p-1',
  name: 'Homepage',
  description: 'Our main site',
  websiteUrl: 'https://example.com',
  status: 'NOT_SCANNED' as const,
  createdAt: '2026-08-13T10:00:00Z',
  updatedAt: '2026-08-13T10:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectsPage />
    </MemoryRouter>,
  )
}

function mockQueries(overrides: Partial<ReturnType<typeof useProjects>> = {}) {
  mockedUseProjects.mockReturnValue({
    data: [PROJECT],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as ReturnType<typeof useProjects>)
}

describe('ProjectsPage', () => {
  // vitest runs without `globals: true`, so RTL's auto-cleanup never fires —
  // unmount explicitly or DOM accumulates across tests in this file.
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue(createAuthValue('authenticated'))
    mockedUseCreateProject.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(undefined),
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as never)
    mockedUseDeleteProject.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as never)
  })

  it('renders the project list', () => {
    mockQueries()

    renderPage()

    expect(screen.getByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.getByText('Homepage')).toBeInTheDocument()
    expect(screen.getByText('https://example.com')).toBeInTheDocument()
    expect(screen.getByText('Not scanned')).toBeInTheDocument()
  })

  it('shows a loading state while fetching', () => {
    mockQueries({ isLoading: true, data: undefined })

    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent('Loading projects')
  })

  it('shows the empty state when there are no projects', () => {
    mockQueries({ data: [] })

    renderPage()

    expect(screen.getByText('No projects yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create your first project' })).toBeInTheDocument()
  })

  it('shows an error state and retries', () => {
    const refetch = vi.fn()
    mockQueries({
      data: undefined,
      isError: true,
      error: new Error('Backend is down'),
      refetch,
    })

    renderPage()

    expect(screen.getByText('Could not load projects')).toBeInTheDocument()
    expect(screen.getByText('Backend is down')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('creates a project through the modal', async () => {
    mockQueries({ data: [] })
    const mutateAsync = vi.fn().mockResolvedValue(undefined)
    mockedUseCreateProject.mockReturnValue({
      mutateAsync,
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as never)

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'New project' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Project name'), {
      target: { value: 'Docs site' },
    })
    fireEvent.change(within(dialog).getByLabelText('Website URL'), {
      target: { value: 'https://docs.example.com' },
    })
    fireEvent.change(within(dialog).getByLabelText('Description (optional)'), {
      target: { value: 'Public docs' },
    })

    fireEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))

    expect(mutateAsync).toHaveBeenCalledWith({
      name: 'Docs site',
      websiteUrl: 'https://docs.example.com',
      description: 'Public docs',
    })
  })

  it('validates the create form before submitting', async () => {
    mockQueries({ data: [] })
    const mutateAsync = vi.fn().mockResolvedValue(undefined)
    mockedUseCreateProject.mockReturnValue({
      mutateAsync,
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    } as never)

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'New project' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))

    expect(await within(dialog).findByText('Enter a project name.')).toBeInTheDocument()
    expect(within(dialog).getByText(/valid URL/)).toBeInTheDocument()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('requires confirmation before deleting a project', () => {
    mockQueries()
    const mutate = vi.fn()
    mockedUseDeleteProject.mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    } as never)

    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Delete Homepage' }))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Delete project?')).toBeInTheDocument()
    expect(mutate).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete project' }))
    expect(mutate).toHaveBeenCalledWith('p-1')
  })

  it('surfaces API errors from the delete mutation', () => {
    mockQueries()
    mockedUseDeleteProject.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: true,
      error: new Error('Project not found.'),
    } as never)

    renderPage()

    expect(screen.getByRole('alert')).toHaveTextContent('Project not found.')
  })
})
