import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { SmartsScreen } from '@/features/smarts/smarts-screen'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const SMARTS = 'GET /api/v1/smarts'
const SHELF = 'GET /api/v1/smarts/shelves/video'
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

function aChapter(overrides: Record<string, unknown> = {}) {
  return {
    id: 'chapter-1',
    kind: 'motif',
    title_key: 'motif',
    title_args: { words: 'Katze · Tier · Innenraum' },
    tags: ['katze', 'tier', 'innenraum'],
    size: 61,
    albums: 23,
    album_id: null,
    from_at: '2017-09-17T15:34:00Z',
    until_at: '2019-10-27T12:00:00Z',
    cover: [aMedium('media-1'), aMedium('media-2'), aMedium('media-3')],
    ...overrides,
  }
}

const body = {
  media: 8142,
  chapters: [
    aChapter({
      id: 'chapter-trip',
      kind: 'trip',
      title_key: 'trip',
      title_args: { place: 'Chessy', days: 4, from: '2016-10-30', until: '2016-11-02' },
      size: 380,
      albums: 1,
      album_id: 'album-1',
    }),
    aChapter(),
    aChapter({
      id: 'chapter-theme',
      kind: 'theme',
      title_key: 'water',
      title_args: { years: 16 },
      size: 199,
    }),
    aChapter({
      id: 'chapter-person',
      kind: 'person',
      title_key: 'pair',
      title_args: { first: 'Olivia', second: 'Matteo' },
      size: 500,
    }),
  ],
  shelves: [
    { key: 'video', count: 61 },
    { key: 'document', count: 68 },
  ],
  faces: [
    {
      person_id: 'person-1',
      name: 'Matteo',
      count: 283,
      face: {
        id: 'face-1',
        media_id: 'media-1',
        box: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.3 },
        second: null,
        crop: '/api/v1/faces/face-1/crop?token=abc',
        person_id: 'person-1',
        assigned_by: null,
        suggested_person_id: null,
        suggested_similarity: null,
      },
    },
  ],
  next_offset: null,
}

beforeEach(() => {
  useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Smarts', () => {
  it('shows the chapters with their names, their size and where they come from', async () => {
    stubApi({ [SMARTS]: { body } })

    await renderScreen(<SmartsScreen />)

    // Every kind writes its own name: a journey in days and a town, a motif in its words,
    // two people in both their names.
    expect(await screen.findByText('4 Tage Chessy')).toBeInTheDocument()
    expect(screen.getByText('Katze · Tier · Innenraum')).toBeInTheDocument()
    expect(screen.getByText('Olivia & Matteo')).toBeInTheDocument()
    // A theme is named by hand and says how far through the archive it runs.
    expect(screen.getByText('Am Wasser')).toBeInTheDocument()
    expect(screen.getByText('über 16 Jahre')).toBeInTheDocument()
    // The size sits on the card, over the pictures.
    expect(screen.getAllByText('61').length).toBeGreaterThan(0)
    // What kind it is, how many folders it draws from, and when it was.
    expect(screen.getAllByText(/aus 23 Alben/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/09\.2017/).length).toBeGreaterThan(0)
  })

  it('offers the shelves with their counts, and the faces that turn up most', async () => {
    stubApi({ [SMARTS]: { body } })

    await renderScreen(<SmartsScreen />)

    expect(await screen.findByText('Videos')).toBeInTheDocument()
    expect(screen.getByText('68')).toBeInTheDocument()
    expect(screen.getByText('Matteo')).toBeInTheDocument()
    expect(screen.getByText('283')).toBeInTheDocument()
  })

  it('leads from a chapter card into that chapter', async () => {
    stubApi({ [SMARTS]: { body } })

    await renderScreen(<SmartsScreen />)
    const card = await screen.findByRole('link', { name: /Katze · Tier · Innenraum/ })

    expect(card).toHaveAttribute('href', expect.stringContaining('/smarts/chapter-1'))
  })

  it('says what is missing when no chapter has been built yet', async () => {
    stubApi({
      [SMARTS]: { body: { media: 0, chapters: [], shelves: [], faces: [], next_offset: null } },
    })

    await renderScreen(<SmartsScreen />)

    expect(await screen.findByText('Noch keine Kapitel')).toBeInTheDocument()
    expect(screen.getByText(/entstehen nachts/)).toBeInTheDocument()
  })

  it('shows one shelf as a grid of its media', async () => {
    stubApi({
      [SMARTS]: { body },
      [SHELF]: { body: { key: 'video', items: [aMedium('media-9')], next_offset: null } },
      [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } },
    })

    await renderScreen(<SmartsScreen shelf="video" />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Videos' })).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: 'Zurück zu Smarts' })).toBeInTheDocument()
  })

  it('the dice opens a chapter as a slideshow', async () => {
    stubApi({ [SMARTS]: { body } })

    const { router } = await renderScreen(<SmartsScreen />)
    await userEvent.click(await screen.findByRole('button', { name: 'Würfeln' }))

    await waitFor(() => {
      expect(router.state.location.pathname).toMatch(/\/smarts\/chapter-/)
    })
    expect(router.state.location.search).toEqual({ play: true })
  })
})
