/**
 * The session as the network layer sees it: the access token in memory and the single place that
 * exchanges a refresh token for a new pair.
 *
 * The access token is deliberately never written to localStorage or sessionStorage - anything on
 * the page could read it there. It lives for the lifetime of the tab and is restored on start by
 * refreshing, which is what the refresh token is for.
 */

import { type Problem, problemFromResponse } from '@/api/problem'
import { serverOrigin } from '@/platform/server'
import { tokenStorage } from '@/platform/token-storage'

export const API_BASE = '/api/v1'

/**
 * Absolute URL for an API path.
 *
 * The browser would resolve a relative one against the document, but Request outside a document
 * does not, so every call is spelled out - and on a phone the document is the app itself, which
 * is not where the server is. Hence the origin rather than the page.
 */
export function apiUrl(path: string): string {
  return new URL(path, serverOrigin() || location.origin).toString()
}

export interface SessionTokens {
  accessToken: string
  /** Only the native app receives one; browsers get an httpOnly cookie instead. */
  refreshToken?: string | null | undefined
}

let accessToken: string | null = null
let refreshInFlight: Promise<string> | null = null
let onSessionLost: (() => void) | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export async function rememberTokens(tokens: SessionTokens): Promise<void> {
  accessToken = tokens.accessToken
  if (tokens.refreshToken) await tokenStorage.write(tokens.refreshToken)
}

export async function forgetTokens(): Promise<void> {
  accessToken = null
  await tokenStorage.clear()
}

/** Called when refreshing fails, so the app can fall back to the login screen. */
export function onSessionEnded(handler: () => void): void {
  onSessionLost = handler
}

export class SessionExpiredError extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title)
    this.name = 'SessionExpiredError'
    this.problem = problem
  }
}

/**
 * Exchange the refresh token for a new pair.
 *
 * Several requests can hit a 401 at the same time; they all wait on the same exchange, because the
 * server rotates the token and treats a second use of the old one as a replay - which would revoke
 * the whole family and log the user out for good.
 */
export function refreshSession(): Promise<string> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

async function performRefresh(): Promise<string> {
  const stored = tokenStorage.kind === 'native' ? await tokenStorage.read() : null

  const response = await fetch(apiUrl(`${API_BASE}/auth/refresh`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ refresh_token: stored }),
  })

  if (!response.ok) {
    const problem = await problemFromResponse(response)
    await forgetTokens()
    onSessionLost?.()
    throw new SessionExpiredError(problem)
  }

  const tokens = (await response.json()) as { access_token: string; refresh_token: string | null }
  await rememberTokens({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token })
  return tokens.access_token
}
