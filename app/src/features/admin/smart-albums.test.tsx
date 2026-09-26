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
  chapters: 125,
  media: 13100,
  built_at: '2026-09-26T03:30:00Z',
  by_kind: { day: 35, motif: 40, person: 29, trip: 11, place: 8, ritual: 2 },
  max_media: 500,
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
  it('says what they hold, and of which kinds', async () => {
    stubApi({ [STATE]: { body: state } })

    await renderScreen(<SmartAlbums />)

    expect(
      await screen.findByText(/125 Kapitel mit 13.100 Medien, höchstens 500 je Kapitel/),
    ).toBeInTheDocument()
    expect(screen.getByText(/40 Motiv, 35 Tag, 29 Person, 11 Reise/)).toBeInTheDocument()
  })

  it('asks for 21 motifs unless another number is typed', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { chapters: 125, media: 13100, by_kind: { motif: 21 } } },
    })

    await renderScreen(<SmartAlbums />)
    expect(await screen.findByLabelText('Motive')).toHaveValue(21)

    await userEvent.click(screen.getByRole('button', { name: 'Neu erstellen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST')).toBe(true)
    })
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ chapters: 21 })
    expect(await screen.findByRole('status')).toHaveTextContent(
      '125 Kapitel mit 13.100 Medien neu erstellt.',
    )
  })

  it('sends the number that was typed', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { chapters: 5, media: 100, by_kind: { motif: 5 } } },
    })

    await renderScreen(<SmartAlbums />)
    const field = await screen.findByLabelText('Motive')
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
    const field = await screen.findByLabelText('Motive')
    await userEvent.clear(field)

    expect(screen.getByRole('button', { name: 'Neu erstellen' })).toBeDisabled()
  })
})
