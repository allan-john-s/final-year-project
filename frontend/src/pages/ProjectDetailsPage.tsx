import { ArrowLeft, Calendar, Globe, Loader2, RefreshCw, Save, Trash2 } from 'lucide-react'
import { useState, type ChangeEvent, type ComponentProps, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { FormError } from '@/components/auth/FormError'
import { AppHeader } from '@/components/layout/AppHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDeleteProject, useProject, useUpdateProject } from '@/hooks/useProjects'
import { validateProject, type ProjectErrors } from '@/lib/projectValidation'
import type { Project, ProjectStatus } from '@/services/projectService'

type BadgeVariant = ComponentProps<typeof Badge>['variant']

const STATUS_STYLE: Record<ProjectStatus, { label: string; variant: BadgeVariant }> = {
  NOT_SCANNED: { label: 'Not scanned', variant: 'outline' },
  SCANNING: { label: 'Scanning', variant: 'secondary' },
  SCANNED: { label: 'Scanned', variant: 'default' },
  FAILED: { label: 'Failed', variant: 'destructive' },
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

interface ProjectEditFormProps {
  project: Project
  isSaving: boolean
  saveError: unknown
  onSave: (input: { name: string; websiteUrl: string; description: string }) => Promise<void>
}

/**
 * Edit form for a project. Initialized from `project` on mount; the parent
 * keys it by project id so navigating between projects remounts fresh state.
 */
function ProjectEditForm({ project, isSaving, saveError, onSave }: ProjectEditFormProps) {
  const [name, setName] = useState(project.name)
  const [websiteUrl, setWebsiteUrl] = useState(project.websiteUrl)
  const [description, setDescription] = useState(project.description)
  const [errors, setErrors] = useState<ProjectErrors>({})

  function clearFieldError(field: keyof ProjectErrors) {
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validateProject({ name, description, websiteUrl })
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }
    setErrors({})
    await onSave({
      name: name.trim(),
      websiteUrl: websiteUrl.trim(),
      description: description.trim(),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="details-name">Project name</Label>
        <Input
          id="details-name"
          value={name}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            setName(event.target.value)
            if (errors.name) clearFieldError('name')
          }}
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={errors.name ? 'details-name-error' : undefined}
        />
        {errors.name ? (
          <p id="details-name-error" role="alert" className="text-sm text-destructive">
            {errors.name}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="details-url">Website URL</Label>
        <Input
          id="details-url"
          type="url"
          value={websiteUrl}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            setWebsiteUrl(event.target.value)
            if (errors.websiteUrl) clearFieldError('websiteUrl')
          }}
          aria-invalid={errors.websiteUrl ? true : undefined}
          aria-describedby={errors.websiteUrl ? 'details-url-error' : undefined}
        />
        {errors.websiteUrl ? (
          <p id="details-url-error" role="alert" className="text-sm text-destructive">
            {errors.websiteUrl}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="details-description">Description</Label>
        <Input
          id="details-description"
          value={description}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            setDescription(event.target.value)
            if (errors.description) clearFieldError('description')
          }}
          aria-invalid={errors.description ? true : undefined}
          aria-describedby={errors.description ? 'details-description-error' : undefined}
        />
        {errors.description ? (
          <p id="details-description-error" role="alert" className="text-sm text-destructive">
            {errors.description}
          </p>
        ) : null}
      </div>

      <FormError message={saveError instanceof Error ? saveError.message : null} />

      <div className="flex justify-end">
        <Button type="submit" disabled={isSaving} aria-busy={isSaving}>
          {isSaving ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Saving…
            </>
          ) : (
            <>
              <Save className="size-4" aria-hidden="true" />
              Save changes
            </>
          )}
        </Button>
      </div>
    </form>
  )
}

export function ProjectDetailsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { data: project, isLoading, isError, error, refetch } = useProject(projectId)
  const updateProject = useUpdateProject()
  const deleteProject = useDeleteProject()
  const [confirmOpen, setConfirmOpen] = useState(false)

  async function handleSave(input: { name: string; websiteUrl: string; description: string }) {
    if (!project) return
    await updateProject.mutateAsync({ id: project.id, input })
  }

  async function handleDelete() {
    if (!project) return
    setConfirmOpen(false)
    await deleteProject.mutateAsync(project.id)
    navigate('/projects', { replace: true })
  }

  if (isLoading) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto flex max-w-3xl flex-col items-center gap-3 px-6 py-24 text-muted-foreground">
          <Loader2 className="size-6 animate-spin" aria-hidden="true" />
          <span role="status" className="text-sm">
            Loading project…
          </span>
        </main>
      </div>
    )
  }

  if (isError || !project) {
    return (
      <div className="min-h-svh bg-background text-foreground antialiased">
        <AppHeader />
        <main className="mx-auto max-w-3xl px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>Project unavailable</CardTitle>
              <CardDescription>
                {error instanceof Error ? error.message : 'The project could not be loaded.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button variant="outline" asChild>
                <Link to="/projects">
                  <ArrowLeft className="size-4" aria-hidden="true" />
                  Back to projects
                </Link>
              </Button>
              <Button variant="outline" onClick={() => void refetch()}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Try again
              </Button>
            </CardContent>
          </Card>
        </main>
      </div>
    )
  }

  const status = STATUS_STYLE[project.status]

  return (
    <div className="min-h-svh bg-background text-foreground antialiased">
      <AppHeader />

      <main className="mx-auto max-w-3xl px-6 py-12">
        <Button variant="ghost" size="sm" asChild className="mb-4 -ml-2">
          <Link to="/projects">
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to projects
          </Link>
        </Button>

        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Globe className="size-3.5" aria-hidden="true" />
              {project.websiteUrl}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={status.variant}>{status.label}</Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmOpen(true)}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="size-4" aria-hidden="true" />
              Delete
            </Button>
          </div>
        </div>

        <Card className="gap-4">
          <CardHeader>
            <CardTitle className="text-base">Details</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              <Calendar className="size-3.5" aria-hidden="true" />
              Created {formatDate(project.createdAt)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ProjectEditForm
              key={project.id}
              project={project}
              isSaving={updateProject.isPending}
              saveError={updateProject.isError ? updateProject.error : null}
              onSave={handleSave}
            />
          </CardContent>
        </Card>

        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete project?</DialogTitle>
              <DialogDescription>
                “{project.name}” and all of its future scan data will be permanently removed. This
                action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={() => void handleDelete()}>
                Delete project
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  )
}
