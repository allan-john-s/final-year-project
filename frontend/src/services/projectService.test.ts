import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/lib/api'

import { projectService } from './projectService'

vi.mock('@/lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedApi = vi.mocked(apiClient)

const ROW = {
  id: 'p-1',
  name: 'Homepage',
  description: 'Our main site',
  website_url: 'https://example.com',
  status: 'NOT_SCANNED',
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:00:00Z',
}

describe('projectService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('lists projects and maps snake_case responses to camelCase', async () => {
    mockedApi.get.mockResolvedValue({ data: [ROW] })

    const projects = await projectService.listProjects()

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/projects')
    expect(projects[0]).toEqual({
      id: 'p-1',
      name: 'Homepage',
      description: 'Our main site',
      websiteUrl: 'https://example.com',
      status: 'NOT_SCANNED',
      createdAt: '2026-08-13T10:00:00Z',
      updatedAt: '2026-08-13T10:00:00Z',
    })
  })

  it('fetches a single project', async () => {
    mockedApi.get.mockResolvedValue({ data: ROW })

    const project = await projectService.getProject('p-1')

    expect(mockedApi.get).toHaveBeenCalledWith('/api/v1/projects/p-1')
    expect(project.websiteUrl).toBe('https://example.com')
  })

  it('creates a project with snake_case payload', async () => {
    mockedApi.post.mockResolvedValue({ data: ROW })

    await projectService.createProject({
      name: 'Homepage',
      websiteUrl: 'https://example.com',
      description: 'Our main site',
    })

    expect(mockedApi.post).toHaveBeenCalledWith('/api/v1/projects', {
      name: 'Homepage',
      description: 'Our main site',
      website_url: 'https://example.com',
    })
  })

  it('updates only the fields provided', async () => {
    mockedApi.patch.mockResolvedValue({ data: ROW })

    await projectService.updateProject('p-1', { name: 'Renamed' })

    expect(mockedApi.patch).toHaveBeenCalledWith('/api/v1/projects/p-1', { name: 'Renamed' })
  })

  it('updates status values as-is', async () => {
    mockedApi.patch.mockResolvedValue({ data: ROW })

    await projectService.updateProject('p-1', { status: 'SCANNING' })

    expect(mockedApi.patch).toHaveBeenCalledWith('/api/v1/projects/p-1', { status: 'SCANNING' })
  })

  it('deletes a project', async () => {
    mockedApi.delete.mockResolvedValue({ data: undefined })

    await projectService.deleteProject('p-1')

    expect(mockedApi.delete).toHaveBeenCalledWith('/api/v1/projects/p-1')
  })
})
