import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { projectService } from '@/services/projectService'

import { useCreateProject, useDeleteProject, useProjects } from './useProjects'

vi.mock('@/services/projectService', () => ({
  projectService: {
    listProjects: vi.fn(),
    getProject: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
  },
}))

const mockedService = vi.mocked(projectService)

const PROJECT = {
  id: 'p-1',
  name: 'Homepage',
  description: '',
  websiteUrl: 'https://example.com',
  status: 'NOT_SCANNED' as const,
  createdAt: '2026-08-13T10:00:00Z',
  updatedAt: '2026-08-13T10:00:00Z',
}

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('project hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('useProjects fetches the project list', async () => {
    mockedService.listProjects.mockResolvedValue([PROJECT])

    const { result } = renderHook(() => useProjects(), {
      wrapper: makeWrapper(makeQueryClient()),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedService.listProjects).toHaveBeenCalledOnce()
    expect(result.current.data).toEqual([PROJECT])
  })

  it('useCreateProject submits and refreshes the list', async () => {
    mockedService.listProjects.mockResolvedValue([])
    mockedService.createProject.mockResolvedValue(PROJECT)

    const queryClient = makeQueryClient()
    const wrapper = makeWrapper(queryClient)

    // Keep the list query mounted so invalidation triggers a refetch.
    const list = renderHook(() => useProjects(), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))
    expect(mockedService.listProjects).toHaveBeenCalledTimes(1)

    const { result } = renderHook(() => useCreateProject(), { wrapper })
    await result.current.mutateAsync({
      name: 'Homepage',
      websiteUrl: 'https://example.com',
    })

    expect(mockedService.createProject).toHaveBeenCalledWith({
      name: 'Homepage',
      websiteUrl: 'https://example.com',
    })
    await waitFor(() => expect(mockedService.listProjects).toHaveBeenCalledTimes(2))
  })

  it('useDeleteProject removes and refreshes the list', async () => {
    mockedService.listProjects.mockResolvedValue([])
    mockedService.deleteProject.mockResolvedValue(undefined)

    const queryClient = makeQueryClient()
    const wrapper = makeWrapper(queryClient)

    const list = renderHook(() => useProjects(), { wrapper })
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true))

    const { result } = renderHook(() => useDeleteProject(), { wrapper })
    await result.current.mutateAsync('p-1')

    expect(mockedService.deleteProject).toHaveBeenCalledWith('p-1')
    await waitFor(() => expect(mockedService.listProjects).toHaveBeenCalledTimes(2))
  })
})
