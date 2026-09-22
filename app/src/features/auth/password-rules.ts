/** Matches the server: at least this many characters, with a letter and a digit among them. */
export const MIN_PASSWORD_LENGTH = 8

export type PasswordProblem = 'tooShort' | 'noLetter' | 'noDigit'

/**
 * Checks a password the way the server does, so the form can answer immediately instead of
 * bouncing off a 422. Other characters are welcome, they are just not required.
 */
export function passwordProblem(password: string): PasswordProblem | null {
  if (password.length < MIN_PASSWORD_LENGTH) return 'tooShort'
  if (!/\p{L}/u.test(password)) return 'noLetter'
  if (!/\d/u.test(password)) return 'noDigit'
  return null
}
