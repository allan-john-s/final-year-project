import { Loader2 } from 'lucide-react'
import { useState, type ChangeEvent, type FormEvent } from 'react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FormError } from '@/components/auth/FormError'
import { validateProject, type ProjectErrors } from '@/lib/projectValidation'
import type { ProjectCreateInput } from '@/services/projectService'

interface CreateProjectModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with a validated payload; the parent owns the mutation. */
  onSubmit: (input: ProjectCreateInput) => Promise<void>
}

export function CreateProjectModal({ open, onOpenChange, onSubmit }: CreateProjectModalProps) {
  const [name, setName] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<ProjectErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function clearFieldError(field: keyof ProjectErrors) {
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  function resetForm() {
    setName('')
    setWebsiteUrl('')
    setDescription('')
    setErrors({})
    setSubmitError(null)
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm()
    onOpenChange(next)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validateProject({ name, description, websiteUrl })
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }
    setErrors({})
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      await onSubmit({
        name: name.trim(),
        websiteUrl: websiteUrl.trim(),
        description: description.trim(),
      })
      resetForm()
      onOpenChange(false)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Could not create the project.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>
            Add a website you want to analyze for accessibility.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              placeholder="Company homepage"
              value={name}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setName(event.target.value)
                if (errors.name) clearFieldError('name')
              }}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'project-name-error' : undefined}
            />
            {errors.name ? (
              <p id="project-name-error" role="alert" className="text-sm text-destructive">
                {errors.name}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="project-url">Website URL</Label>
            <Input
              id="project-url"
              type="url"
              placeholder="https://example.com"
              value={websiteUrl}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setWebsiteUrl(event.target.value)
                if (errors.websiteUrl) clearFieldError('websiteUrl')
              }}
              aria-invalid={errors.websiteUrl ? true : undefined}
              aria-describedby={errors.websiteUrl ? 'project-url-error' : undefined}
            />
            {errors.websiteUrl ? (
              <p id="project-url-error" role="alert" className="text-sm text-destructive">
                {errors.websiteUrl}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="project-description">Description (optional)</Label>
            <Input
              id="project-description"
              placeholder="What should be analyzed?"
              value={description}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setDescription(event.target.value)
                if (errors.description) clearFieldError('description')
              }}
              aria-invalid={errors.description ? true : undefined}
              aria-describedby={errors.description ? 'project-description-error' : undefined}
            />
            {errors.description ? (
              <p id="project-description-error" role="alert" className="text-sm text-destructive">
                {errors.description}
              </p>
            ) : null}
          </div>

          <FormError message={submitError} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Creating…
                </>
              ) : (
                'Create project'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
