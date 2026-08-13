/**
 * Client-side validation for project forms.
 *
 * Mirrors the backend rules in `app/schemas/projects.py`: name 1–100
 * characters, description ≤ 2000, and an http(s) website URL with a host.
 */

export interface ProjectErrors {
  name?: string
  description?: string
  websiteUrl?: string
}

const NAME_MAX = 100
const DESCRIPTION_MAX = 2000

export function isValidWebsiteUrl(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed || /\s/.test(trimmed)) return false
  try {
    const url = new URL(trimmed)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function validateProject(input: {
  name: string
  description: string
  websiteUrl: string
}): ProjectErrors {
  const errors: ProjectErrors = {}

  const name = input.name.trim()
  if (!name) {
    errors.name = 'Enter a project name.'
  } else if (name.length > NAME_MAX) {
    errors.name = `Project name must be at most ${NAME_MAX} characters.`
  }

  if (input.description.length > DESCRIPTION_MAX) {
    errors.description = `Description must be at most ${DESCRIPTION_MAX} characters.`
  }

  if (!isValidWebsiteUrl(input.websiteUrl)) {
    errors.websiteUrl = 'Enter a valid URL starting with http:// or https://.'
  }

  return errors
}
