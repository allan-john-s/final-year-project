import { Calendar, Globe, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useState, type ComponentProps } from 'react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { Project, ProjectStatus } from '@/services/projectService'

const STATUS_STYLE: Record<ProjectStatus, { label: string; variant: ComponentProps<typeof Badge>['variant'] }> = {
  NOT_SCANNED: { label: 'Not scanned', variant: 'outline' },
  SCANNING: { label: 'Scanning', variant: 'secondary' },
  SCANNED: { label: 'Scanned', variant: 'default' },
  FAILED: { label: 'Failed', variant: 'destructive' },
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

interface ProjectCardProps {
  project: Project
  /** Called after the user confirms deletion in the confirmation dialog. */
  onDelete: (project: Project) => void
}

export function ProjectCard({ project, onDelete }: ProjectCardProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const status = STATUS_STYLE[project.status]

  return (
    <Card className="gap-4">
      <CardHeader className="gap-2 [.border-b]:pb-4">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{project.name}</CardTitle>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
        <CardDescription className="flex items-center gap-1.5">
          <Globe className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">{project.websiteUrl}</span>
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {project.description ? (
          <p className="line-clamp-2 text-sm text-muted-foreground">{project.description}</p>
        ) : null}
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Calendar className="size-3.5" aria-hidden="true" />
            Created {formatDate(project.createdAt)}
          </span>
          <div className="flex items-center gap-1">
            <Button asChild variant="ghost" size="sm">
              <Link to={`/projects/${project.id}`}>Details</Link>
            </Button>
            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
              <DialogTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={`Delete ${project.name}`}>
                  <Trash2 className="size-4" aria-hidden="true" />
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete project?</DialogTitle>
                  <DialogDescription>
                    “{project.name}” and all of its future scan data will be permanently removed.
                    This action cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => {
                      setConfirmOpen(false)
                      onDelete(project)
                    }}
                  >
                    Delete project
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
