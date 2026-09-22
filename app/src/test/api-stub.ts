import { vi } from 'vitest'

interface StubbedResponse {
  status?: number
  body?: unknown
  /** Problem Details, as the API returns them for every failure. */
  problem?: { type: string; title: string; status: number; detail?: string } & Record<
    string,
    unknown
  >
}

/**
 * Answers the app's fetch calls from a small table of routes, e.g.
 * `{ 'POST /api/v1/auth/login': { body: tokens } }`. Anything not listed fails the test loudly,
 * so a screen that quietly calls an endpoint nobody expected does not pass.
 */
/**
 * What screens ask in the background - the bell's number, the news, the persons row - answered empty
 * unless a test says otherwise, and left out of `calls`: they belong to the frame, not the
 * screen under test.
 */
const BACKGROUND: Record<string, StubbedResponse> = {
  'GET /api/v1/notifications/unread': { body: { count: 0 } },
  'GET /api/v1/activity': { body: { items: [], next_cursor: null } },
  // The persons row above the search: nobody named yet.
  'GET /api/v1/people': {
    body: { persons: [], groups: { items: [], next_cursor: null }, suggestions: 0 },
  },
}

export function stubApi(routes: Record<string, StubbedResponse>) {
  const calls: { method: string; path: string; url: string; body: unknown }[] = []

  const fetchStub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init)
    const path = new URL(request.url, 'http://test').pathname
    const key = `${request.method} ${path}`

    const background = !(key in routes) && key in BACKGROUND
    if (!background) {
      calls.push({ method: request.method, path, url: request.url, body: await readBody(request) })
    }

    const route = routes[key] ?? BACKGROUND[key]
    if (!route) throw new Error(`Unexpected request: ${key}`)

    const status = route.status ?? (route.problem ? route.problem.status : 200)
    const payload = route.problem ?? route.body ?? null

    return new Response(payload === null ? null : JSON.stringify(payload), {
      status,
      headers: {
        'Content-Type': route.problem ? 'application/problem+json' : 'application/json',
      },
    })
  })

  vi.stubGlobal('fetch', fetchStub)
  return { calls, fetchStub }
}

async function readBody(request: Request): Promise<unknown> {
  try {
    const text = await request.clone().text()
    return text ? (JSON.parse(text) as unknown) : null
  } catch {
    return null
  }
}

export const aUser = {
  id: '00000000-0000-0000-0000-000000000001',
  username: 'anna',
  email: 'anna@muninn.local',
  display_name: 'Anna Bauer',
  role: 'user' as const,
  status: 'active' as const,
  must_change_password: false,
  created_at: '2026-09-01T10:00:00Z',
  last_login_at: '2026-09-19T22:00:00Z',
}

export const aTokenResponse = {
  access_token: 'access-token-1',
  token_type: 'bearer' as const,
  expires_at: '2026-09-19T22:15:00Z',
  refresh_token: null,
  user: aUser,
}
