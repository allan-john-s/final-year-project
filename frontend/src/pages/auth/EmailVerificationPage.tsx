import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { AuthShell } from '@/components/auth/AuthShell'
import { FormError } from '@/components/auth/FormError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { isNonEmpty } from '@/lib/validation'

type VerificationState = 'idle' | 'verifying' | 'verified' | 'failed'

export function EmailVerificationPage() {
  const { verifyEmail } = useAuth()
  const [searchParams] = useSearchParams()
  const urlToken = searchParams.get('token')

  const [state, setState] = useState<VerificationState>(urlToken ? 'verifying' : 'idle')
  const [token, setToken] = useState(urlToken ?? '')
  const [tokenError, setTokenError] = useState<string | undefined>()
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (urlToken) {
      verifyEmail(urlToken)
        .then(() => setState('verified'))
        .catch(() => setState('failed'))
    }
  }, [urlToken, verifyEmail])

  async function handleManualSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isNonEmpty(token)) {
      setTokenError('Enter the verification token from your email.')
      return
    }
    setTokenError(undefined)
    setSubmitError(null)
    setState('verifying')
    try {
      await verifyEmail(token.trim())
      setState('verified')
    } catch (error) {
      setState('failed')
      setSubmitError(error instanceof Error ? error.message : 'Verification failed.')
    }
  }

  if (state === 'verifying') {
    return (
      <AuthShell title="Verifying your email" description="This should only take a moment.">
        <div className="flex flex-col items-center gap-4 py-6" role="status" aria-live="polite">
          <Loader2 className="size-8 animate-spin text-primary" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">Verifying your email address…</p>
        </div>
      </AuthShell>
    )
  }

  if (state === 'verified') {
    return (
      <AuthShell title="Email verified" description="Your email address is confirmed.">
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <CheckCircle2 className="size-6" aria-hidden="true" />
          </span>
          <p className="text-sm text-muted-foreground">
            You can now sign in and start using the framework.
          </p>
          <Button asChild className="mt-2">
            <Link to="/login">Go to sign in</Link>
          </Button>
        </div>
      </AuthShell>
    )
  }

  if (state === 'failed') {
    return (
      <AuthShell title="Verification failed" description="We could not verify that token.">
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <XCircle className="size-6" aria-hidden="true" />
          </span>
          <p className="text-sm text-muted-foreground">
            The link may be expired or invalid. Try the token below, or request a new verification
            email.
          </p>
          <form onSubmit={handleManualSubmit} className="w-full space-y-4" noValidate>
            <div className="space-y-2 text-left">
              <Label htmlFor="token">Verification token</Label>
              <Input
                id="token"
                value={token}
                onChange={(event) => {
                  setToken(event.target.value)
                  if (tokenError) setTokenError(undefined)
                }}
                aria-invalid={tokenError ? true : undefined}
                aria-describedby={tokenError ? 'token-error' : undefined}
              />
              {tokenError ? (
                <p id="token-error" role="alert" className="text-sm text-destructive">
                  {tokenError}
                </p>
              ) : null}
            </div>
            <FormError message={submitError} />
            <Button type="submit" className="w-full">
              Try again
            </Button>
          </form>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Verify your email"
      description="Paste the token from your verification email."
    >
      <form onSubmit={handleManualSubmit} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="token">Verification token</Label>
          <Input
            id="token"
            value={token}
            onChange={(event) => {
              setToken(event.target.value)
              if (tokenError) setTokenError(undefined)
            }}
            placeholder="Paste your token"
            aria-invalid={tokenError ? true : undefined}
            aria-describedby={tokenError ? 'token-error' : undefined}
          />
          {tokenError ? (
            <p id="token-error" role="alert" className="text-sm text-destructive">
              {tokenError}
            </p>
          ) : null}
        </div>
        <FormError message={submitError} />
        <Button type="submit" className="w-full">
          Verify email
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
