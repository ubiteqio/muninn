import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { MediaGrid } from '@/features/media/media-grid'

function aMedium(overrides: Partial<Medium> = {}): Medium {
  return {
    id: 'media-1',
    album_id: 'album-italien',
    kind: 'image',
    status: 'active',
    taken_at: '2009-07-14T15:30:12Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: null,
    camera_make: null,
    camera_model: null,
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: '2009 Italien/IMG_1.jpg',
      filename: 'IMG_1.jpg',
      byte_size: 4_200_000,
    },
    urls: {
      thumb: '/api/v1/media/media-1/thumb?token=abc',
      preview: null,
      video: null,
      poster: null,
      original: '/api/v1/media/media-1/original?token=abc',
    },
    files: [],
    ...overrides,
  }
}

describe('MediaGrid', () => {
  it('says which picture was asked for', async () => {
    const onOpen = vi.fn()
    render(
      <MediaGrid media={[aMedium(), aMedium({ id: 'media-2' })]} columns={3} onOpen={onOpen} />,
    )

    const [, second] = screen.getAllByRole('button')
    await userEvent.click(second as HTMLElement)

    expect(onOpen).toHaveBeenCalledWith(1)
  })

  it('stands in for a picture whose preview is still being made', () => {
    render(
      <MediaGrid
        media={[aMedium({ urls: { ...aMedium().urls, thumb: null } })]}
        columns={3}
        onOpen={vi.fn()}
      />,
    )

    expect(screen.getByRole('button').querySelector('img')).toBeNull()
  })
})
