import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AlbumPlace } from '@/features/albums/album-place'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const FLORENCE = {
  id: 3176959,
  name: 'Florenz',
  region: 'Toskana',
  country: 'Italien',
  estimated: false,
}

describe('AlbumPlace', () => {
  it('finds a town by its name and gives it to the album', async () => {
    const { calls } = stubApi({
      'GET /api/v1/albums/album-1': { body: { id: 'album-1', place: null } },
      'GET /api/v1/places': { body: { items: [FLORENCE] } },
      'PUT /api/v1/albums/album-1/place': { body: { id: 'album-1', place: FLORENCE } },
    })
    const user = userEvent.setup()

    await renderScreen(<AlbumPlace albumId="album-1" />)
    await user.click(await screen.findByRole('button', { name: 'Ort' }))
    await user.type(screen.getByLabelText('Ort suchen – z. B. Florenz'), 'Flor')
    await user.click(await screen.findByRole('button', { name: /Florenz.*Toskana, Italien/ }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({ place_id: FLORENCE.id })
    })
  })

  it('shows the place it has and takes it away again', async () => {
    const { calls } = stubApi({
      'GET /api/v1/albums/album-1': { body: { id: 'album-1', place: FLORENCE } },
      'PUT /api/v1/albums/album-1/place': { body: { id: 'album-1', place: null } },
    })
    const user = userEvent.setup()

    await renderScreen(<AlbumPlace albumId="album-1" />)
    await user.click(await screen.findByRole('button', { name: 'Florenz' }))
    await user.click(screen.getByRole('button', { name: 'Entfernen' }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({ place_id: null })
    })
  })
})
