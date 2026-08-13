/**
 * Client-side form validation for the auth flows.
 *
 * Validation mirrors what the backend will enforce once a provider is
 * connected, but stays dependency-free so it can run everywhere.
 */

export interface SignInErrors {
  email?: string
  password?: string
}

export interface SignUpErrors {
  displayName?: string
  email?: string
  password?: string
  confirmPassword?: string
}

export interface ResetPasswordErrors {
  newPassword?: string
  confirmPassword?: string
}

export function isNonEmpty(value: string): boolean {
  return value.trim().length > 0
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export function isValidEmail(email: string): boolean {
  return EMAIL_PATTERN.test(email)
}

export function isValidPassword(password: string): boolean {
  return password.length >= 8 && /[a-zA-Z]/.test(password) && /\d/.test(password)
}

export function passwordsMatch(a: string, b: string): boolean {
  return a === b
}

const PASSWORD_MESSAGE = 'Password must be at least 8 characters and include a letter and a number.'
const EMAIL_MESSAGE = 'Enter a valid email address.'
const MISMATCH_MESSAGE = 'Passwords do not match.'

export function validateSignIn(input: { email: string; password: string }): SignInErrors {
  const errors: SignInErrors = {}
  if (!isValidEmail(input.email)) errors.email = EMAIL_MESSAGE
  if (!isNonEmpty(input.password)) errors.password = 'Enter your password.'
  return errors
}

export function validateSignUp(input: {
  displayName: string
  email: string
  password: string
  confirmPassword: string
}): SignUpErrors {
  const errors: SignUpErrors = {}
  if (!isValidEmail(input.email)) errors.email = EMAIL_MESSAGE
  if (!isValidPassword(input.password)) errors.password = PASSWORD_MESSAGE
  if (!passwordsMatch(input.password, input.confirmPassword)) {
    errors.confirmPassword = MISMATCH_MESSAGE
  }
  return errors
}

export function validateResetPassword(input: {
  newPassword: string
  confirmPassword: string
}): ResetPasswordErrors {
  const errors: ResetPasswordErrors = {}
  if (!isValidPassword(input.newPassword)) errors.newPassword = PASSWORD_MESSAGE
  if (!passwordsMatch(input.newPassword, input.confirmPassword)) {
    errors.confirmPassword = MISMATCH_MESSAGE
  }
  return errors
}
