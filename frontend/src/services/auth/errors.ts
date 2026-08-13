/** Error types shared across auth providers. */

export class AuthError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'AuthError'
  }
}

/** Thrown by the placeholder service until a real provider is connected. */
export class AuthNotImplementedError extends AuthError {
  constructor(operation: string) {
    super(
      `Authentication is not implemented yet (${operation}). ` +
        'A provider will be wired up in a later module.',
    )
    this.name = 'AuthNotImplementedError'
  }
}

/** Thrown when Supabase credentials are missing from the environment. */
export class AuthConfigurationError extends AuthError {
  constructor(message: string) {
    super(message)
    this.name = 'AuthConfigurationError'
  }
}

/**
 * Thrown on sign-up when the provider created the account but requires email
 * confirmation before a session exists. The UI surfaces the friendly message.
 */
export class AuthEmailVerificationRequiredError extends AuthError {
  constructor() {
    super('Account created — check your email to verify your address, then sign in.')
    this.name = 'AuthEmailVerificationRequiredError'
  }
}
