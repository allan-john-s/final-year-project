/**
 * Project React Query hooks.
 *
 * Data fetching is centralized here (never in components): queries cache and
 * share project data, mutations invalidate the relevant keys so the UI stays
 * consistent after create/update/delete.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  projectService,
  type ProjectCreateInput,
  type ProjectUpdateInput,
} from '@/services/projectService'

export const projectsKey = ['projects'] as const

export function projectKey(id: string) {
  return ['projects', id] as const
}

/** Fetch all projects owned by the current user. */
export function useProjects() {
  return useQuery({
    queryKey: projectsKey,
    queryFn: () => projectService.listProjects(),
  })
}

/** Fetch a single project. Disabled until a valid id is provided. */
export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: projectKey(id ?? ''),
    queryFn: () => projectService.getProject(id as string),
    enabled: Boolean(id),
  })
}

/** Create a project, then refresh the list. */
export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProjectCreateInput) => projectService.createProject(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectsKey })
    },
  })
}

/** Update a project, then refresh the list and the detail view. */
export function useUpdateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: ProjectUpdateInput }) =>
      projectService.updateProject(id, input),
    onSuccess: (_project, { id }) => {
      void queryClient.invalidateQueries({ queryKey: projectsKey })
      void queryClient.invalidateQueries({ queryKey: projectKey(id) })
    },
  })
}

/** Delete a project, then refresh the list. */
export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => projectService.deleteProject(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectsKey })
    },
  })
}
