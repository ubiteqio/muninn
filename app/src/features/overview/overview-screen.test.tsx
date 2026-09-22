import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { OverviewScreen } from '@/features/overview/overview-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const REPORT = {
  totals: {
    media: 4776,
    photos: 4490,
    videos: 286,
    bytes: 39133009439,
    derived_bytes: 7623566541,
    video_seconds: 13100,
    albums: 202,
    first_taken: '1999-06-18T13:55:01Z',
    last_taken: '2023-06-27T20:13:03Z',
  },
  years: [
    { year: 1999, photos: 6, videos: 0 },
    { year: 2000, photos: 578, videos: 4 },
  ],
  pipeline: [
    { step: 'descriptions', done: 4776, of: 4776 },
    { step: 'faces', done: 2000, of: 4776 },
  ],
  content: {
    frames: 8877,
    videos_with_speech: 249,
    spoken_seconds: 8344,
    screenshots: 354,
    documents: 74,
    with_text: 1371,
  },
  tags: [
    { name: 'sonne', count: 1179 },
    { name: 'kind', count: 696 },
  ],
  scenes: [],
  times_of_day: [{ name: 'tag', count: 3000 }],
  people: {
    faces: 6919,
    named: 3973,
    suggested: 0,
    unnamed: 2946,
    groups: 355,
    persons: 31,
    media_with_faces: 2801,
  },
  persons: [{ id: 'lena', name: 'Lena', media: 812, crop: '/crop/lena' }],
  places: { with_gps: 1340, estimated: 0, towns: 70, countries: 6 },
  countries: [{ name: 'Deutschland', count: 1100 }],
  towns: [{ name: 'München', country: 'Deutschland', count: 79 }],
  date_sources: [
    { name: 'exif', count: 4316 },
    { name: 'folder_name', count: 366 },
  ],
  cameras: [{ name: 'Apple iPhone 6s', count: 2220 }],
  duplicates: { groups: 169, exact: 10, near: 61, burst: 98, hidden: 12 },
  social: { reactions: 40, comments: 12, favorites: 8, users: 3 },
}

describe('OverviewScreen', () => {
  it('shows the library at a glance', async () => {
    useAuthStore.setState({ user: { role: 'admin' } as never })
    stubApi({ 'GET /api/v1/overview': { body: REPORT } })

    await renderScreen(<OverviewScreen />)

    expect(await screen.findByText('4.776')).toBeInTheDocument()
    // Four cards of the same shape, in this order: media in their albums, photos, videos with
    // their length, and the room it all takes.
    const totals = within(screen.getByRole('region', { name: 'Die Bibliothek in Zahlen' }))
    const labels = totals.getAllByText(/^(Medien|Fotos|Videos|Speicher)/)
    expect(labels.map((label) => label.textContent)).toEqual([
      'Medien',
      'Fotos',
      'Videos',
      'Speicher der Originale',
    ])
    expect(totals.getByText('Medien').closest('[class*="p-4"]')).toHaveTextContent(
      /in [\d.]+ Alben/,
    )
    expect(screen.getByText('36,4 GB')).toBeInTheDocument()
    expect(screen.getByText('dazu 7,1 GB Vorschauen')).toBeInTheDocument()
    expect(screen.getByText('3 h 38 min lang')).toBeInTheDocument()
    expect(screen.getByText('1999 – 2023 · 25 Jahre')).toBeInTheDocument()
    expect(screen.getByText('31 Personen benannt')).toBeInTheDocument()
    expect(screen.getByText('Lena')).toBeInTheDocument()
    expect(screen.getByText('2.000 / 4.776')).toBeInTheDocument()
    expect(screen.getByText('Kamera (EXIF)')).toBeInTheDocument()
  })
})
