import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MemoriesSection } from '@/features/memories/memories-section'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aPhoto(id: string) {
  return {
    id,
    album_id: 'album-1',
    kind: 'image',
    status: 'active',
    taken_at: '2019-09-21T10:00:00Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 4000,
    height: 3000,
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
      relative_path: `Rom/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 1,
    },
    urls: {
      thumb: `/thumb/${id}`,
      preview: `/preview/${id}`,
      video: null,
      poster: null,
      original: '/o',
    },
    files: [],
  }
}

describe('MemoriesSection', () => {
  it('shows a card per year with the album, the day and the number of photos', async () => {
    stubApi({
      'GET /api/v1/memories': {
        body: {
          day: '2026-09-21',
          items: [
            {
              id: 'memory-1',
              year: 2019,
              years_ago: 7,
              taken_on: '2019-09-21',
              from_week: false,
              album_id: 'album-1',
              title: 'Rom 2019',
              media: [aPhoto('a'), aPhoto('b')],
            },
            {
              id: 'memory-2',
              year: 2025,
              years_ago: 1,
              taken_on: '2025-09-19',
              from_week: true,
              album_id: null,
              title: null,
              media: [aPhoto('c')],
            },
          ],
        },
      },
    })

    await renderScreen(<MemoriesSection />)

    const rome = await screen.findByRole('button', { name: /Heute vor 7 Jahren: Rom 2019/ })
    expect(within(rome).getByText('21. September 2019 · 2 Fotos')).toBeInTheDocument()
    const lastYear = screen.getByRole('button', { name: /Diese Woche vor einem Jahr: 2025/ })
    expect(within(lastYear).getByText('19. September 2025 · 1 Foto')).toBeInTheDocument()
  })
})
