/**
 * Project service — the single place that talks to the projects API.
 *
 * Components and hooks depend on this module (never on axios directly). All
 * requests go through `@/lib/api`, which attaches the Supabase bearer token
 * and normalizes errors into `ApiError`.
 */
import { apiClient } from '@/lib/api'

export type ProjectStatus = 'NOT_SCANNED' | 'SCANNING' | 'SCANNED' | 'FAILED'

export interface Project {
  id: string
  name: string
  description: string
  websiteUrl: string
  status: ProjectStatus
  createdAt: string
  updatedAt: string
}

export interface ProjectCreateInput {
  name: string
  description?: string
  websiteUrl: string
}

export interface ProjectUpdateInput {
  name?: string
  description?: string
  websiteUrl?: string
  status?: ProjectStatus
}

interface ProjectRow {
  id: string
  name: string
  description: string
  website_url: string
  status: ProjectStatus
  created_at: string
  updated_at: string
}

function mapProject(row: ProjectRow): Project {
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    websiteUrl: row.website_url,
    status: row.status,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

class ProjectService {
  async listProjects(): Promise<Project[]> {
    const { data } = await apiClient.get<ProjectRow[]>('/api/v1/projects')
    return data.map(mapProject)
  }

  async getProject(id: string): Promise<Project> {
    const { data } = await apiClient.get<ProjectRow>(`/api/v1/projects/${id}`)
    return mapProject(data)
  }

  async createProject(input: ProjectCreateInput): Promise<Project> {
    const { data } = await apiClient.post<ProjectRow>('/api/v1/projects', {
      name: input.name,
      description: input.description ?? '',
      website_url: input.websiteUrl,
    })
    return mapProject(data)
  }

  async updateProject(id: string, input: ProjectUpdateInput): Promise<Project> {
    const payload: Record<string, unknown> = {}
    if (input.name !== undefined) payload.name = input.name
    if (input.description !== undefined) payload.description = input.description
    if (input.websiteUrl !== undefined) payload.website_url = input.websiteUrl
    if (input.status !== undefined) payload.status = input.status
    const { data } = await apiClient.patch<ProjectRow>(`/api/v1/projects/${id}`, payload)
    return mapProject(data)
  }

  async deleteProject(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/projects/${id}`)
  }
}

/** Shared singleton — hooks and pages consume this instance. */
export const projectService = new ProjectService()
