import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { forgetTokens } from '@/api/session'
import { useAuthStore } from '@/features/auth/auth-store'
import { SessionGate } from '@/features/auth/session-gate'
import { aTokenResponse, aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const LOGIN = 'POST /api/v1/auth/login'

beforeEach(async () => {
  await forgetTokens()
  useAuthStore.setState({ status: 'signed-out', user: null, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function signIn(username: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Benutzername'), username)
  await user.type(screen.getByLabelText('Passwort'), password)
  await user.click(screen.getByRole('button', { name: 'Anmelden' }))
}

describe('login screen', () => {
  it('signs the user in', async () => {
    stubApi({ [LOGIN]: { body: aTokenResponse } })
    await renderScreen(
      <SessionGate>
        <p>Angemeldet</p>
      </SessionGate>,
    )

    await signIn('anna', 'ein-gutes-passwort7')

    expect(await screen.findByText('Angemeldet')).toBeInTheDocument()
  })

  it('says what is wrong when the password does not match', async () => {
    stubApi({
      [LOGIN]: {
        problem: {
          type: 'urn:muninn:problem:invalid-credentials',
          title: 'Invalid credentials',
          status: 401,
        },
      },
    })
    await renderScreen(<SessionGate>{null}</SessionGate>)

    await signIn('anna', 'falsch')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Benutzername oder Passwort ist falsch.',
    )
  })

  it('says how long to wait after too many attempts', async () => {
    stubApi({
      [LOGIN]: {
        problem: {
          type: 'urn:muninn:problem:too-many-login-attempts',
          title: 'Too many login attempts',
          status: 429,
          retry_after_seconds: 120,
        },
      },
    })
    await renderScreen(<SessionGate>{null}</SessionGate>)

    await signIn('anna', 'falsch')

    expect(await screen.findByRole('alert')).toHaveTextContent('in 2 Minuten')
  })

  it('asks for a new password while the starting one is in place', async () => {
    stubApi({
      [LOGIN]: { body: { ...aTokenResponse, user: { ...aUser, must_change_password: true } } },
      'POST /api/v1/auth/password': { body: aTokenResponse },
    })
    await renderScreen(
      <SessionGate>
        <p>Angemeldet</p>
      </SessionGate>,
    )

    await signIn('anna', 'z37o-j2ps-zw9t')

    expect(await screen.findByRole('heading', { name: 'Passwort festlegen' })).toBeInTheDocument()
    expect(screen.queryByText('Angemeldet')).not.toBeInTheDocument()
  })

  it('does not send a request when the server is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    await renderScreen(<SessionGate>{null}</SessionGate>)

    await signIn('anna', 'ein-gutes-passwort7')

    expect(await screen.findByRole('alert')).toHaveTextContent('Server ist nicht erreichbar')
  })
})
