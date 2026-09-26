import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { ChapterScreen } from '@/features/smarts/chapter-screen'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const CHAPTER = 'GET /api/v1/smarts/chapters/chapter-1'
const ABILITIES = 'GET /api/v1/search/abilities'

function aMedium(id: string) {
  return {
    id,
    album_id: 'album-1',
    kind: 'image' as const,
    status: 'active' as const,
    taken_at: '2018-03-24T15:30:12Z',
    taken_at_source: 'exif' as const,
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
      root_id: 'root-1',
      root_name: 'Fotos',
      relative_path: `Heap/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 30801,
    },
    urls: {
      thumb: `/api/v1/media/${id}/thumb?token=abc`,
      preview: `/api/v1/media/${id}/preview?token=abc`,
      video: null,
      poster: null,
      original: `/api/v1/media/${id}/original?token=abc`,
    },
    files: [],
  }
}

const body = {
  chapter: {
    id: 'chapter-1',
    album_id: 'album-1',
    album_title: '2018 Budapest',
    title: 'Katze · Tier · Innenraum',
    tags: ['katze', 'tier', 'innenraum'],
    size: 3,
    from_at: '2018-03-24T15:30:12Z',
    until_at: '2018-03-24T18:30:12Z',
    cover: [aMedium('media-1')],
  },
  items: [aMedium('media-1'), aMedium('media-2'), aMedium('media-3')],
  next_offset: null,
}

const abilities = { pictures: true, meanings: true, ready: true }

beforeEach(() => {
  useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('one chapter', () => {
  it('names it, counts it and says which folder it comes from', async () => {
    stubApi({ [CHAPTER]: { body }, [ABILITIES]: { body: abilities } })

    await renderScreen(<ChapterScreen chapterId="chapter-1" />)

    expect(await screen.findByText(/3 Medien/)).toBeInTheDocument()
    expect(screen.getByText(/2018 Budapest/)).toBeInTheDocument()
    // The words the name was made of stand under it, as the pictures' own tags.
    expect(screen.getByText('katze')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zum Ordner' })).toHaveAttribute(
      'href',
      expect.stringContaining('/albums/album-1'),
    )
  })

  it('shows its media and leads back to the Smarts', async () => {
    stubApi({ [CHAPTER]: { body }, [ABILITIES]: { body: abilities } })

    await renderScreen(<ChapterScreen chapterId="chapter-1" />)

    expect(await screen.findAllByRole('button', { name: /Bild vom|Medium/ })).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Zurück zu Smarts' })).toHaveAttribute(
      'href',
      '/smarts',
    )
  })

  it('opens the same viewer as the albums and the search, with the same buttons', async () => {
    stubApi({ [CHAPTER]: { body }, [ABILITIES]: { body: abilities } })

    await renderScreen(<ChapterScreen chapterId="chapter-1" medium="media-1" />, {
      path: '/smarts/chapter-1',
    })

    expect(await screen.findByRole('button', { name: 'Details anzeigen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ähnliche Bilder' })).toBeInTheDocument()
  })

  it('offers nothing to compare when there is no picture model', async () => {
    stubApi({
      [CHAPTER]: { body },
      [ABILITIES]: { body: { pictures: false, meanings: true, ready: true } },
    })

    await renderScreen(<ChapterScreen chapterId="chapter-1" medium="media-1" />, {
      path: '/smarts/chapter-1',
    })

    expect(await screen.findByRole('button', { name: 'Details anzeigen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ähnliche Bilder' })).not.toBeInTheDocument()
  })
})
