import { QueryClient } from '@tanstack/react-query'
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
  chapters: 92,
  media: 4241,
  built_at: '2026-09-26T03:30:00Z',
  by_kind: { day: 35, motif: 7, person: 29, trip: 11, place: 8, ritual: 2 },
  max_chapters: 60,
  max_media: 50,
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

    expect(await screen.findByText(/Zurzeit 92 Smart-Alben mit 4.241 Medien/)).toBeInTheDocument()
    expect(screen.getByText(/35 Tag, 29 Person, 11 Reise, 8 Ort, 7 Motiv/)).toBeInTheDocument()
  })

  it('builds with the numbers that are saved, asking for nothing itself', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { chapters: 60, media: 3000, by_kind: { motif: 10 } } },
    })

    await renderScreen(<SmartAlbums />)
    await userEvent.click(await screen.findByRole('button', { name: 'Neu erstellen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST')).toBe(true)
    })
    // The settings decide; the button carries no number of its own.
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({})
    expect(await screen.findByRole('status')).toHaveTextContent(
      '60 Smart-Alben mit 3.000 Medien neu erstellt.',
    )
  })

  it('throws away the chapters it had in hand: a run writes new ones', async () => {
    const { calls } = stubApi({
      [STATE]: { body: state },
      [BUILD]: { body: { chapters: 5, media: 100, by_kind: { motif: 5 } } },
      'GET /api/v1/smarts': {
        body: { media: 8000, chapters: [], shelves: [], faces: [], next_offset: null },
      },
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    // What somebody looked at before pressing the button.
    client.setQueryData(['smarts'], { chapters: ['von vorher'] })

    await renderScreen(<SmartAlbums />, { client })
    await userEvent.click(await screen.findByRole('button', { name: 'Neu erstellen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST')).toBe(true)
    })
    await waitFor(() => {
      expect(client.getQueryData(['smarts'])).toBeUndefined()
    })
  })
})
