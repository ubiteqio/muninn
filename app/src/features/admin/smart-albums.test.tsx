import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SmartAlbums } from '@/features/admin/smart-albums'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const STATE = 'GET /api/v1/smarts/state'
const BUILD = 'POST /api/v1/smarts/build'

const state = {
  chapters: 486,
  albums: 70,
  media: 4291,
  outstanding: 3,
  built_at: '2026-09-26T03:30:00Z',
  wanted: 21,
}

beforeEach(() => {
  useAuthStore.setState({
    status: 'signed-in',
    needsPasswordChange: false,
    user: { ...aUser, role: 'admin' },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('building the Smarts by hand', () => {
  it('says what they hold and what is still outstanding', async () => {
    stubApi({ [STATE]: { body: state } })

    await renderScreen(<SmartAlbums />)

    expect(await screen.findByText(/486 Kapitel in 70 Alben/)).toBeInTheDocument()
    expect(screen.getByText(/3 Alben ohne Kapitel/)).toBeInTheDocument()
  })

  it('asks for 21 chapters unless another number is typed', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { albums: 2, chapters: 22, outstanding: 1 } },
    })

    await renderScreen(<SmartAlbums />)
    expect(await screen.findByLabelText('Kapitel')).toHaveValue(21)

    await userEvent.click(screen.getByRole('button', { name: 'Neu erstellen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST')).toBe(true)
    })
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ chapters: 21 })
    expect(await screen.findByRole('status')).toHaveTextContent(
      '22 Kapitel in 2 Alben neu erstellt.',
    )
  })

  it('sends the number that was typed', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { albums: 1, chapters: 5, outstanding: 0 } },
    })

    await renderScreen(<SmartAlbums />)
    const field = await screen.findByLabelText('Kapitel')
    await userEvent.clear(field)
    await userEvent.type(field, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Neu erstellen' }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ chapters: 5 })
    })
  })

  it('does not send a number nobody could mean', async () => {
    stubApi({ [STATE]: { body: state } })

    await renderScreen(<SmartAlbums />)
    const field = await screen.findByLabelText('Kapitel')
    await userEvent.clear(field)

    expect(screen.getByRole('button', { name: 'Neu erstellen' })).toBeDisabled()
  })

  it('says plainly when there was nothing left to build', async () => {
    stubApi({
      [STATE]: { body: { ...state, outstanding: 0 } },
      [BUILD]: { body: { albums: 0, chapters: 0, outstanding: 0 } },
    })

    await renderScreen(<SmartAlbums />)
    await userEvent.click(await screen.findByRole('button', { name: 'Neu erstellen' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Alle Alben sind auf dem neuesten Stand.',
    )
  })
})
