/**
 * Errors from the API arrive as Problem Details (RFC 9457). This turns them into something the
 * screens can branch on, and keeps unexpected failures - a dead server, a proxy error - in the
 * same shape so no caller has to handle two kinds of error.
 */

export interface Problem {
  type: string
  title: string
  status: number
  detail?: string
  /** Extension members, e.g. retry_after_seconds on a throttled login. */
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly problem: Problem

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title)
    this.name = 'ApiError'
    this.problem = problem
  }

  /** Compares against the stable part of the problem type, e.g. "invalid-credentials". */
  is(slug: string): boolean {
    return this.problem.type === `urn:muninn:problem:${slug}`
  }

  get status(): number {
    return this.problem.status
  }

  get retryAfterSeconds(): number | undefined {
    const value = this.problem['retry_after_seconds']
    return typeof value === 'number' ? value : undefined
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export async function problemFromResponse(response: Response): Promise<Problem> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'title' in body && 'status' in body) {
      return body as Problem
    }
  } catch {
    // Not JSON, or no body at all: fall through to the generic problem below.
  }

  return {
    type: 'about:blank',
    title: response.statusText || 'Request failed',
    status: response.status,
  }
}
