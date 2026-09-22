import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isApiError } from '@/api/problem'
import { forgetTokens, getAccessToken } from '@/api/session'
import { useAuthStore } from '@/features/auth/auth-store'
import { aTokenResponse, aUser, stubApi } from '@/test/api-stub'

const LOGIN = 'POST /api/v1/auth/login'
const REFRESH = 'POST /api/v1/auth/refresh'
const LOGOUT = 'POST /api/v1/auth/logout'
const PASSWORD = 'POST /api/v1/auth/password'
const ME = 'GET /api/v1/me'

beforeEach(async () => {
  await forgetTokens()
  useAuthStore.setState({ status: 'unknown', user: null, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('signing in', () => {
  it('keeps the user and the access token', async () => {
    const { calls } = stubApi({ [LOGIN]: { body: aTokenResponse } })

    await useAuthStore.getState().signIn('anna', 'ein-gutes-passwort7')

    expect(useAuthStore.getState().status).toBe('signed-in')
    expect(useAuthStore.getState().user?.display_name).toBe('Anna Bauer')
    expect(getAccessToken()).toBe('access-token-1')
    expect(calls[0]?.body).toMatchObject({ username: 'anna', client: 'web' })
  })

  it('reports wrong credentials as such', async () => {
    stubApi({
      [LOGIN]: {
        problem: {
          type: 'urn:muninn:problem:invalid-credentials',
          title: 'Invalid credentials',
          status: 401,
        },
      },
    })

    const failure = await useAuthStore
      .getState()
      .signIn('anna', 'falsch')
      .catch((error: unknown) => error)

    expect(isApiError(failure) && failure.is('invalid-credentials')).toBe(true)
    expect(useAuthStore.getState().status).toBe('unknown')
    expect(getAccessToken()).toBeNull()
  })

  it('passes on how long a throttled login has to wait', async () => {
    stubApi({
      [LOGIN]: {
        problem: {
          type: 'urn:muninn:problem:too-many-login-attempts',
          title: 'Too many login attempts',
          status: 429,
          retry_after_seconds: 240,
        },
      },
    })

    const failure = await useAuthStore
      .getState()
      .signIn('anna', 'falsch')
      .catch((error: unknown) => error)

    expect(isApiError(failure) && failure.retryAfterSeconds).toBe(240)
  })

  it('goes to the password screen while the starting password is in place', async () => {
    stubApi({
      [LOGIN]: { body: { ...aTokenResponse, user: { ...aUser, must_change_password: true } } },
    })

    await useAuthStore.getState().signIn('anna', 'z37o-j2ps-zw9t')

    expect(useAuthStore.getState().needsPasswordChange).toBe(true)
  })
})

describe('restoring a session', () => {
  it('signs in again from the refresh token', async () => {
    stubApi({
      [REFRESH]: { body: { access_token: 'access-token-2', refresh_token: null } },
      [ME]: { body: aUser },
    })

    await useAuthStore.getState().restore()

    expect(useAuthStore.getState().status).toBe('signed-in')
    expect(getAccessToken()).toBe('access-token-2')
  })

  it('ends up signed out when the refresh token is gone', async () => {
    stubApi({
      [REFRESH]: {
        problem: {
          type: 'urn:muninn:problem:invalid-refresh-token',
          title: 'Invalid refresh token',
          status: 401,
        },
      },
    })

    await useAuthStore.getState().restore()

    expect(useAuthStore.getState().status).toBe('signed-out')
    expect(useAuthStore.getState().user).toBeNull()
  })
})

describe('signing out', () => {
  it('tells the server and forgets the token', async () => {
    const { calls } = stubApi({
      [LOGIN]: { body: aTokenResponse },
      [LOGOUT]: { status: 204 },
    })
    await useAuthStore.getState().signIn('anna', 'ein-gutes-passwort7')

    await useAuthStore.getState().signOut()

    expect(calls.some((call) => call.path === '/api/v1/auth/logout')).toBe(true)
    expect(useAuthStore.getState().status).toBe('signed-out')
    expect(getAccessToken()).toBeNull()
  })

  it('signs out locally even when the server cannot be reached', async () => {
    stubApi({ [LOGIN]: { body: aTokenResponse } })
    await useAuthStore.getState().signIn('anna', 'ein-gutes-passwort7')

    // No logout route in the stub: the request throws, and this device is signed out anyway.
    await useAuthStore
      .getState()
      .signOut()
      .catch(() => undefined)

    expect(useAuthStore.getState().status).toBe('signed-out')
    expect(getAccessToken()).toBeNull()
  })
})

describe('setting the own password', () => {
  it('stays signed in on this device with the fresh tokens', async () => {
    stubApi({
      [LOGIN]: { body: { ...aTokenResponse, user: { ...aUser, must_change_password: true } } },
      [PASSWORD]: {
        body: {
          ...aTokenResponse,
          access_token: 'access-token-after-change',
          user: { ...aUser, must_change_password: false },
        },
      },
    })
    await useAuthStore.getState().signIn('anna', 'z37o-j2ps-zw9t')

    await useAuthStore.getState().setPassword('z37o-j2ps-zw9t', 'mein-eigenes-passwort5')

    expect(useAuthStore.getState().status).toBe('signed-in')
    expect(useAuthStore.getState().needsPasswordChange).toBe(false)
    expect(getAccessToken()).toBe('access-token-after-change')
  })

  it('reports a wrong current password without changing anything', async () => {
    stubApi({
      [LOGIN]: { body: aTokenResponse },
      [PASSWORD]: {
        problem: {
          type: 'urn:muninn:problem:invalid-credentials',
          title: 'Invalid credentials',
          status: 401,
        },
      },
    })
    await useAuthStore.getState().signIn('anna', 'ein-gutes-passwort7')

    const failure = await useAuthStore
      .getState()
      .setPassword('falsch', 'mein-eigenes-passwort5')
      .catch((error: unknown) => error)

    expect(isApiError(failure) && failure.is('invalid-credentials')).toBe(true)
    expect(useAuthStore.getState().status).toBe('signed-in')
  })
})
