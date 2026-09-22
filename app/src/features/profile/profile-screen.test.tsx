import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { ProfileScreen } from '@/features/profile/profile-screen'
import { aTokenResponse, aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const PASSWORD = 'POST /api/v1/auth/password'

function signedInAs(role: 'user' | 'admin') {
  useAuthStore.setState({
    status: 'signed-in',
    user: { ...aUser, role },
    needsPasswordChange: false,
  })
}

beforeEach(() => {
  signedInAs('user')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function changePassword(current: string, next: string, repeat = next) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Aktuelles Passwort'), current)
  await user.type(screen.getByLabelText('Neues Passwort'), next)
  await user.type(screen.getByLabelText('Neues Passwort wiederholen'), repeat)
  await user.click(screen.getByRole('button', { name: 'Passwort ändern' }))
}

describe('profile', () => {
  it('changes the password and stays signed in', async () => {
    stubApi({ [PASSWORD]: { body: aTokenResponse } })
    await renderScreen(<ProfileScreen />)

    await changePassword('ein-gutes-passwort7', 'mein-neues-passwort8')

    expect(await screen.findByRole('status')).toHaveTextContent('Passwort geändert')
    expect(useAuthStore.getState().status).toBe('signed-in')
  })

  it('refuses a password that is too short before asking the server', async () => {
    const { calls } = stubApi({})
    await renderScreen(<ProfileScreen />)

    await changePassword('ein-gutes-passwort7', 'kurz1')

    expect(await screen.findByRole('alert')).toHaveTextContent('mindestens 8 Zeichen')
    expect(calls.filter((call) => call.path.includes('password'))).toHaveLength(0)
  })

  it('refuses a password without a digit before asking the server', async () => {
    const { calls } = stubApi({})
    await renderScreen(<ProfileScreen />)

    await changePassword('ein-gutes-passwort7', 'nurbuchstaben')

    expect(await screen.findByRole('alert')).toHaveTextContent('mindestens eine Zahl')
    expect(calls.filter((call) => call.path.includes('password'))).toHaveLength(0)
  })

  it('refuses a password without a letter before asking the server', async () => {
    const { calls } = stubApi({})
    await renderScreen(<ProfileScreen />)

    await changePassword('ein-gutes-passwort7', '12345678')

    expect(await screen.findByRole('alert')).toHaveTextContent('mindestens einen Buchstaben')
    expect(calls.filter((call) => call.path.includes('password'))).toHaveLength(0)
  })

  it('refuses two passwords that do not match', async () => {
    const { calls } = stubApi({})
    await renderScreen(<ProfileScreen />)

    await changePassword('ein-gutes-passwort7', 'mein-neues-passwort8', 'etwas-ganz-anderes8')

    expect(await screen.findByRole('alert')).toHaveTextContent('stimmen nicht überein')
    expect(calls.filter((call) => call.path.includes('password'))).toHaveLength(0)
  })

  it('says when the current password is wrong', async () => {
    stubApi({
      [PASSWORD]: {
        problem: {
          type: 'urn:muninn:problem:invalid-credentials',
          title: 'Invalid credentials',
          status: 401,
        },
      },
    })
    await renderScreen(<ProfileScreen />)

    await changePassword('falsch', 'mein-neues-passwort8')

    expect(await screen.findByRole('alert')).toHaveTextContent('aktuelle Passwort ist falsch')
  })

  it('does not offer the admin area to a plain user', async () => {
    stubApi({})
    await renderScreen(<ProfileScreen />)

    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('offers the admin area to an admin', async () => {
    stubApi({})
    signedInAs('admin')
    await renderScreen(<ProfileScreen />)

    // The navigation carries a second link of that name for an admin, so look in the page.
    const main = within(screen.getByRole('main'))
    expect(main.getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin')
  })
})
