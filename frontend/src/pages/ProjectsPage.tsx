import { FolderKanban, Loader2, Plus, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { AppHeader } from '@/components/layout/AppHeader'
import { CreateProjectModal } from '@/components/projects/CreateProjectModal'
import { ProjectCard } from '@/components/projects/ProjectCard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useCreateProject, useDeleteProject, useProjects } from '@/hooks/useProjects'
import type { Project } from '@/services/projectService'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

export function ProjectsPage() {
  const { data: projects, isLoading, isError, error, refetch } = useProjects()
  const createProject = useCreateProject()
  const deleteProject = useDeleteProject()
  const [createOpen, setCreateOpen] = useState(false)

  return (
    <div className="min-h-svh bg-background text-foreground antialiased">
      <AppHeader />

      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="mb-8 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Websites you want to analyze for accessibility.
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" aria-hidden="true" />
            New project
          </Button>
        </div>

        {isLoading ? (
          <div
            role="status"
            aria-label="Loading projects"
            className="flex flex-col items-center gap-3 py-24 text-muted-foreground"
          >
            <Loader2 className="size-6 animate-spin" aria-hidden="true" />
            <span className="text-sm">Loading projects…</span>
          </div>
        ) : isError ? (
          <Card>
            <CardHeader>
              <CardTitle>Could not load projects</CardTitle>
              <CardDescription>{errorMessage(error)}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void refetch()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Try again
              </Button>
            </CardContent>
          </Card>
        ) : projects && projects.length === 0 ? (
          <Card>
            <CardHeader>
              <div className="mb-2 flex size-10 items-center justify-center rounded-md bg-accent text-accent-foreground">
                <FolderKanban className="size-5" aria-hidden="true" />
              </div>
              <CardTitle>No projects yet</CardTitle>
              <CardDescription>
                Create your first project to start tracking accessibility issues on a website.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="size-4" aria-hidden="true" />
                Create your first project
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects?.map((project: Project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onDelete={(target) => deleteProject.mutate(target.id)}
              />
            ))}
          </div>
        )}

        {deleteProject.isError ? (
          <p role="alert" className="mt-6 text-sm text-destructive">
            {errorMessage(deleteProject.error)}
          </p>
        ) : null}

        <CreateProjectModal
          open={createOpen}
          onOpenChange={setCreateOpen}
          onSubmit={async (input) => {
            await createProject.mutateAsync(input)
          }}
        />
      </main>
    </div>
  )
}
