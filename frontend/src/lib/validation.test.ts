import { describe, expect, it } from 'vitest'

import {
  isValidEmail,
  isValidPassword,
  passwordsMatch,
  validateResetPassword,
  validateSignIn,
  validateSignUp,
} from './validation'

describe('isValidEmail', () => {
  it('accepts well-formed emails', () => {
    expect(isValidEmail('dev@example.com')).toBe(true)
    expect(isValidEmail('first.last+tag@sub.domain.co')).toBe(true)
  })

  it('rejects malformed emails', () => {
    expect(isValidEmail('')).toBe(false)
    expect(isValidEmail('not-an-email')).toBe(false)
    expect(isValidEmail('a@b')).toBe(false)
    expect(isValidEmail('@example.com')).toBe(false)
    expect(isValidEmail('a b@example.com')).toBe(false)
  })
})

describe('isValidPassword', () => {
  it('accepts passwords with 8+ chars, a letter, and a number', () => {
    expect(isValidPassword('password1')).toBe(true)
    expect(isValidPassword('Aa1b2c3d4')).toBe(true)
  })

  it('rejects weak passwords', () => {
    expect(isValidPassword('short')).toBe(false)
    expect(isValidPassword('onlyletters')).toBe(false)
    expect(isValidPassword('1234567890')).toBe(false)
  })
})

describe('passwordsMatch', () => {
  it('compares two passwords', () => {
    expect(passwordsMatch('secret1', 'secret1')).toBe(true)
    expect(passwordsMatch('secret1', 'secret2')).toBe(false)
  })
})

describe('validateSignIn', () => {
  it('returns no errors for valid input', () => {
    expect(validateSignIn({ email: 'dev@example.com', password: 'anything' })).toEqual({})
  })

  it('flags a missing email and password', () => {
    const errors = validateSignIn({ email: '', password: '' })
    expect(errors.email).toBeTruthy()
    expect(errors.password).toBeTruthy()
  })

  it('flags an invalid email', () => {
    const errors = validateSignIn({ email: 'nope', password: 'x' })
    expect(errors.email).toBe('Enter a valid email address.')
    expect(errors.password).toBeUndefined()
  })
})

describe('validateSignUp', () => {
  it('returns no errors for valid input', () => {
    const errors = validateSignUp({
      displayName: 'Ada',
      email: 'dev@example.com',
      password: 'password1',
      confirmPassword: 'password1',
    })
    expect(errors).toEqual({})
  })

  it('flags a weak password', () => {
    const errors = validateSignUp({
      displayName: '',
      email: 'dev@example.com',
      password: 'weak',
      confirmPassword: 'weak',
    })
    expect(errors.password).toBeTruthy()
  })

  it('flags mismatched passwords', () => {
    const errors = validateSignUp({
      displayName: '',
      email: 'dev@example.com',
      password: 'password1',
      confirmPassword: 'password2',
    })
    expect(errors.confirmPassword).toBe('Passwords do not match.')
  })
})

describe('validateResetPassword', () => {
  it('accepts a strong matching pair', () => {
    expect(
      validateResetPassword({ newPassword: 'password1', confirmPassword: 'password1' }),
    ).toEqual({})
  })

  it('flags weak and mismatched input together', () => {
    const errors = validateResetPassword({ newPassword: 'weak', confirmPassword: 'nomatch' })
    expect(errors.newPassword).toBeTruthy()
    expect(errors.confirmPassword).toBeTruthy()
  })
})
