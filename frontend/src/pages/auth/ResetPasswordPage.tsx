import { Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { AuthShell } from '@/components/auth/AuthShell'
import { FormError } from '@/components/auth/FormError'
import { PasswordInput } from '@/components/auth/PasswordInput'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { isNonEmpty, validateResetPassword, type ResetPasswordErrors } from '@/lib/validation'

export function ResetPasswordPage() {
  const { resetPassword } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [token, setToken] = useState(searchParams.get('token') ?? '')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errors, setErrors] = useState<ResetPasswordErrors>({})
  const [tokenError, setTokenError] = useState<string | undefined>()
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isNonEmpty(token)) {
      setTokenError('Enter the token from your reset email.')
      return
    }
    const nextErrors = validateResetPassword({ newPassword, confirmPassword })
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }
    setErrors({})
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      await resetPassword({ token: token.trim(), newPassword })
      navigate('/login', { replace: true })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Reset failed. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell title="Set a new password" description="Choose a strong password to continue.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="token">Reset token</Label>
          <Input
            id="token"
            value={token}
            onChange={(event) => {
              setToken(event.target.value)
              if (tokenError) setTokenError(undefined)
            }}
            placeholder="Paste the token from your email"
            aria-invalid={tokenError ? true : undefined}
            aria-describedby={tokenError ? 'token-error' : undefined}
          />
          {tokenError ? (
            <p id="token-error" role="alert" className="text-sm text-destructive">
              {tokenError}
            </p>
          ) : null}
        </div>

        <PasswordInput
          id="newPassword"
          label="New password"
          value={newPassword}
          onChange={(event) => {
            setNewPassword(event.target.value)
            if (errors.newPassword) setErrors((current) => ({ ...current, newPassword: undefined }))
          }}
          error={errors.newPassword}
          autoComplete="new-password"
        />

        <PasswordInput
          id="confirmPassword"
          label="Confirm new password"
          value={confirmPassword}
          onChange={(event) => {
            setConfirmPassword(event.target.value)
            if (errors.confirmPassword)
              setErrors((current) => ({ ...current, confirmPassword: undefined }))
          }}
          error={errors.confirmPassword}
          autoComplete="new-password"
        />

        <FormError message={submitError} />

        <Button type="submit" className="w-full" disabled={isSubmitting} aria-busy={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Resetting…
            </>
          ) : (
            'Reset password'
          )}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  )
}
