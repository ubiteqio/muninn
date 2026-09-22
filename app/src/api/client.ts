/**
 * The typed API client. Types come from src/api/generated, which is generated from the server's
 * OpenAPI description with `pnpm gen:api` and never edited by hand.
 */

import createClient from 'openapi-fetch'

import type { paths } from '@/api/generated/schema'
import { ApiError, problemFromResponse } from '@/api/problem'
import { apiUrl, getAccessToken, refreshSession, SessionExpiredError } from '@/api/session'
import { isNative, serverOrigin } from '@/platform/server'

/**
 * Endpoints where a 401 is about credentials, not about an expired token, so refreshing would be
 * beside the point: these are how a session begins and ends, and the password endpoint answers
 * 401 when the current password is wrong.
 */
const NO_REFRESH = ['/auth/login', '/auth/refresh', '/auth/logout', '/auth/password']

function withAuthorization(request: Request, token: string | null): Request {
  if (!token) return request
  const headers = new Headers(request.headers)
  headers.set('Authorization', `Bearer ${token}`)
  return new Request(request, { headers })
}

/** Every address in a value that points into the API, made absolute on the given server. */
function resolveAddresses(value: unknown, origin: string): unknown {
  if (typeof value === 'string') return value.startsWith('/api/') ? `${origin}${value}` : value
  if (Array.isArray(value)) return value.map((item) => resolveAddresses(item, origin))
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, resolveAddresses(item, origin)]),
    )
  }
  return value
}

/**
 * The server names pictures by path - "/api/v1/media/…/thumb?token=…" - which a browser reads
 * against the page it came from, the server itself. The native app is loaded from inside the
 * phone, so there such a path would point at the phone: every address in an answer gets the
 * server in front, once, as the answer arrives.
 */
async function withServerAddresses(response: Response): Promise<Response> {
  const json = response.headers.get('Content-Type')?.includes('json') ?? false
  if (!isNative() || !response.ok || !json || response.status === 204) return response

  const body = resolveAddresses(await response.json(), serverOrigin())
  return new Response(JSON.stringify(body), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  })
}

/**
 * Attaches the access token and, when it has expired, refreshes once and repeats the request.
 * The body is cloned before the first attempt, because a Request can only be read once.
 */
const authenticatedFetch: typeof fetch = async (input, init) => {
  const request = new Request(typeof input === 'string' ? apiUrl(input) : input, init)
  const retryable = !NO_REFRESH.some((path) => new URL(request.url).pathname.endsWith(path))
  const retryCopy = retryable ? request.clone() : null

  const response = await fetch(withAuthorization(request, getAccessToken()))
  if (response.status !== 401 || !retryCopy) return withServerAddresses(response)

  try {
    const token = await refreshSession()
    return await withServerAddresses(await fetch(withAuthorization(retryCopy, token)))
  } catch (error) {
    if (error instanceof SessionExpiredError) return response
    throw error
  }
}

/**
 * The generated paths already carry the /api/v1 prefix, so the calls read exactly as the OpenAPI
 * description spells them. The base is the origin Muninn answers on - the page's own in a
 * browser, the address the phone was given in the native app.
 */
function build() {
  return createClient<paths>({
    baseUrl: serverOrigin() || location.origin,
    credentials: 'include',
    fetch: authenticatedFetch,
  })
}

let client = build()

/**
 * Point the client at another server. The native app does this once, when somebody types the
 * address on the login screen: the base is fixed inside the client, so it gets a new one.
 */
export function apiServerChanged(): void {
  client = build()
}

/**
 * The client itself never changes hands, only what it points at. Every call goes through to
 * whatever is current, so the hundred `api.GET(...)` in the app need to know nothing about it.
 */
export const api = new Proxy({} as ReturnType<typeof build>, {
  get: (_target, key) => Reflect.get(client, key) as unknown,
})

/**
 * Turns an openapi-fetch result into a value or an ApiError, so callers can use try/catch and
 * TanStack Query can treat failures as failures.
 */
export async function unwrap<T>(result: {
  data?: T
  error?: unknown
  response: Response
}): Promise<T> {
  if (result.response.ok && result.data !== undefined) return result.data
  if (result.response.ok) return undefined as T

  const problem =
    result.error && typeof result.error === 'object' && 'status' in result.error
      ? (result.error as Awaited<ReturnType<typeof problemFromResponse>>)
      : await problemFromResponse(result.response.clone())

  throw new ApiError(problem)
}
