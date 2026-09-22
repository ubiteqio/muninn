import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminUsersPage } from '@/features/admin/users-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const LIST = 'GET /api/v1/admin/users'
const CREATE = 'POST /api/v1/admin/users'

const anna = { ...aUser, id: 'user-anna', username: 'anna', display_name: 'Anna Bauer' }
const papa = {
  ...aUser,
  id: 'user-papa',
  username: 'papa',
  display_name: 'Papa',
  role: 'admin' as const,
}

beforeEach(() => {
  useAuthStore.setState({ status: 'signed-in', user: papa, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('user management', () => {
  it('lists the accounts', async () => {
    stubApi({ [LIST]: { body: { items: [anna, papa], next_cursor: null } } })

    await renderScreen(<AdminUsersPage />)

    expect(await screen.findByText('Anna Bauer')).toBeInTheDocument()
    expect(screen.getByText(/^papa/)).toBeInTheDocument()
  })

  it('shows the starting password exactly once, after creating an account', async () => {
    stubApi({
      [LIST]: { body: { items: [papa], next_cursor: null } },
      [CREATE]: {
        status: 201,
        body: { user: anna, starting_password: 'z37o-j2ps-zw9t' },
      },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Konto anlegen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Benutzername'), 'anna')
    await user.type(within(dialog).getByLabelText('Angezeigter Name'), 'Anna Bauer')
    await user.click(within(dialog).getByRole('button', { name: 'Anlegen' }))

    expect(await screen.findByText('z37o-j2ps-zw9t')).toBeInTheDocument()
    expect(screen.getByText(/Nur jetzt lesbar/)).toBeInTheDocument()
  })

  it('says when the username is taken', async () => {
    stubApi({
      [LIST]: { body: { items: [papa], next_cursor: null } },
      [CREATE]: {
        problem: {
          type: 'urn:muninn:problem:name-already-used',
          title: 'Name already used',
          status: 409,
        },
      },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Konto anlegen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Benutzername'), 'papa')
    await user.type(within(dialog).getByLabelText('Angezeigter Name'), 'Noch ein Papa')
    await user.click(within(dialog).getByRole('button', { name: 'Anlegen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('schon vergeben')
  })

  it('refuses to demote the last admin and says why', async () => {
    stubApi({
      [LIST]: { body: { items: [papa], next_cursor: null } },
      'PATCH /api/v1/admin/users/user-papa': {
        problem: {
          type: 'urn:muninn:problem:last-admin',
          title: 'Last admin',
          status: 409,
        },
      },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Papa/ }))
    await user.click(screen.getByRole('radio', { name: 'Benutzer' }))
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('letzte aktive Admin')
  })

  it('hands out a new starting password on reset', async () => {
    stubApi({
      [LIST]: { body: { items: [anna], next_cursor: null } },
      'POST /api/v1/admin/users/user-anna/password': {
        body: { starting_password: 'k7fp-2m9x-qt4w' },
      },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Anna Bauer/ }))
    await user.click(screen.getByRole('button', { name: 'Passwort zurücksetzen' }))

    expect(await screen.findByText('k7fp-2m9x-qt4w')).toBeInTheDocument()
  })

  it('loads the next page on request', async () => {
    stubApi({
      [LIST]: { body: { items: [anna], next_cursor: 'cursor-2' } },
    })
    await renderScreen(<AdminUsersPage />)

    expect(await screen.findByRole('button', { name: 'Weitere laden' })).toBeInTheDocument()
  })

  it('changes the name, username and address of an account', async () => {
    const { calls } = stubApi({
      [LIST]: { body: { items: [anna], next_cursor: null } },
      'PATCH /api/v1/admin/users/user-anna': {
        body: { ...anna, display_name: 'Anna Berg', username: 'anna.berg' },
      },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Anna Bauer/ }))
    const name = screen.getByLabelText('Angezeigter Name')
    await user.clear(name)
    await user.type(name, 'Anna Berg')
    const login = screen.getByLabelText('Benutzername')
    await user.clear(login)
    await user.type(login, 'anna.berg')
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({
        display_name: 'Anna Berg',
        username: 'anna.berg',
      })
    })
  })

  it('deletes an account only after asking', async () => {
    const { calls } = stubApi({
      [LIST]: { body: { items: [anna], next_cursor: null } },
      'DELETE /api/v1/admin/users/user-anna': { status: 204 },
    })
    await renderScreen(<AdminUsersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Anna Bauer/ }))
    await user.click(screen.getByRole('button', { name: 'Konto löschen' }))
    const asked = await screen.findByRole('dialog')
    expect(within(asked).getByText('Konto von „Anna Bauer“ löschen?')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await user.click(within(asked).getByRole('button', { name: 'Endgültig löschen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
    })
  })
})
