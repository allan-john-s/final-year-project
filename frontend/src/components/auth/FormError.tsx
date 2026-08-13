interface FormErrorProps {
  message: string | null
}

/** Submit-level error rendered with an alert role so screen readers announce it. */
export function FormError({ message }: FormErrorProps) {
  if (!message) return null
  return (
    <p
      role="alert"
      className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
    >
      {message}
    </p>
  )
}
