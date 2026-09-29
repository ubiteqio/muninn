import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AdminDuplicatesPage } from '@/features/admin/duplicates-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aMedium(id: string, filename: string, width: number) {
  return {
    id,
    album_id: 'album-1',
    kind: 'image',
    status: 'active',
    taken_at: '2009-07-14T15:30:00Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width,
    height: (width * 3) / 4,
    duration_seconds: null,
    camera_make: null,
    camera_model: null,
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: id,
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: `Urlaub/${filename}`,
      filename,
      byte_size: 1_000_000,
    },
    urls: { thumb: `/thumb/${id}`, preview: null, video: null, poster: null, original: '/o' },
    files: [],
  }
}

describe('AdminDuplicatesPage', () => {
  it('asks for the heaviest groups first when told to', async () => {
    // A group of two 4K videos is worth forty photographs of a birthday, and working through
    // copies is usually about winning back room.
    useAuthStore.setState({ user: { role: 'admin' } as never })
    const { calls } = stubApi({
      'GET /api/v1/admin/duplicates': { body: { items: [], next_cursor: null } },
    })
    await renderScreen(<AdminDuplicatesPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Größte zuerst' }))

    await waitFor(() => {
      const asked = calls.filter((call) => call.path === '/api/v1/admin/duplicates').at(-1)
      expect(new URL(asked?.url ?? '', 'http://test').searchParams.get('sort')).toBe('size')
    })
  })

  it('keeps the suggested copy and hides the other', async () => {
    useAuthStore.setState({ user: { role: 'admin' } as never })
    const { calls } = stubApi({
      'GET /api/v1/admin/duplicates': {
        body: {
          open_count: 1,
          next_cursor: null,
          items: [
            {
              id: 7,
              kind: 'near',
              members: [
                { media: aMedium('m-1', 'DSC_1.jpg', 4000), best: true, hidden: false },
                {
                  media: aMedium('m-2', 'IMG-20090714-WA0001.jpg', 1600),
                  best: false,
                  hidden: false,
                },
              ],
            },
          ],
        },
      },
      'POST /api/v1/admin/duplicates/7/keep': { status: 204 },
    })
    const user = userEvent.setup()

    await renderScreen(<AdminDuplicatesPage />)

    expect(await screen.findByText('Kopie in anderer Größe oder Qualität')).toBeInTheDocument()
    expect(screen.getByText('Empfohlen')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Behalten, Rest ausblenden' }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ media_ids: ['m-1'] })
    })
  })
})
