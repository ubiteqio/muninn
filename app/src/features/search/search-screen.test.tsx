import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { period, SearchScreen } from '@/features/search/search-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const SEARCH = 'POST /api/v1/search'
const ABILITIES = 'GET /api/v1/search/abilities'

function aMedium(id: string, kind: 'image' | 'video' = 'image'): Medium {
  return {
    id,
    album_id: 'album-1',
    kind,
    status: 'active',
    taken_at: '2012-07-14T12:00:00Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: kind === 'video' ? 95 : null,
    camera_make: null,
    camera_model: null,
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: `Urlaub/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 1000,
    },
    urls: {
      thumb: `/api/v1/media/${id}/thumb?token=a`,
      preview: `/api/v1/media/${id}/preview?token=a`,
      video: kind === 'video' ? `/api/v1/media/${id}/video?token=a` : null,
      poster: null,
      original: `/api/v1/media/${id}/original?token=a`,
    },
    files: [],
  }
}

function aPage(items: { media: Medium; moment?: number | null }[], extra: object = {}) {
  return {
    items: items.map((item) => ({ moment: null, ...item })),
    next_cursor: null,
    understood: { text: 'Strand', date_from: null, date_until: null, kind: null },
    degraded: false,
    ...extra,
  }
}

describe('SearchScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the grid it is about to fill instead of a line of text', async () => {
    // A line of text under the chips and then a screen full of pictures: the page unfolded
    // under the eye. Now the tiles land in rows that are already there.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    )

    await renderScreen(<SearchScreen q="Strand" />)

    const results = screen.getByRole('region', { name: 'Suchergebnisse' })
    expect(results).toHaveAttribute('aria-busy', 'true')
    expect(within(results).getByText('Wird gesucht …')).toBeInTheDocument()
    expect(results.querySelectorAll('.placeholder').length).toBeGreaterThan(8)
  })

  it('holds the row of people before it is known whether there are any', async () => {
    // The row decides from the answer whether it stands at all. Without this the hint below
    // starts under the search field and is pushed down a moment later.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    )

    await renderScreen(<SearchScreen />)

    const row = screen.getByRole('region', { name: 'Personen' })
    expect(row).toHaveAttribute('aria-busy', 'true')
    expect(within(row).getByText('Wird geladen …')).toBeInTheDocument()
  })

  it('says what can be asked before anything is typed, and searches nothing', async () => {
    const { calls } = stubApi({ [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } } })

    await renderScreen(<SearchScreen />)

    expect(await screen.findByText(/Beschreibe, was du suchst/)).toBeInTheDocument()
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([ABILITIES])
  })

  it('offers the plain search while the machine behind the models is away', async () => {
    // Set up but not answering: promising to search the pictures themselves would be a lie.
    stubApi({ [ABILITIES]: { body: { pictures: true, meanings: true, ready: false } } })

    await renderScreen(<SearchScreen />)

    expect(await screen.findByText(/Der KI-Server antwortet gerade nicht/)).toBeInTheDocument()
    expect(screen.queryByText(/Beschreibe, was du suchst/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Bibliothek durchsuchen')).toHaveAttribute(
      'placeholder',
      'Suchen – z. B. „Oma am Strand 2012“',
    )
  })

  it('asks to be described to while the models answer', async () => {
    stubApi({ [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } } })

    await renderScreen(<SearchScreen />)

    await waitFor(() => {
      expect(screen.getByLabelText('Bibliothek durchsuchen')).toHaveAttribute(
        'placeholder',
        'Beschreibe, was du suchst – z. B. „Oma am Strand 2012“',
      )
    })
    expect(screen.getByRole('button', { name: 'Suchen' })).toBeDisabled()
  })

  it('narrows a search by a year the library actually has', async () => {
    const { calls } = stubApi({
      [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } },
      [SEARCH]: {
        body: {
          ...aPage([{ media: aMedium('strand') }]),
          // What the found media are made of, which is what the filters offer.
          facets: { years: [{ value: '2012', label: '2012', count: 42 }] },
        },
      },
    })
    await renderScreen(<SearchScreen q="Strand" year={2012} />, { path: '/search' })

    // One year is asked for as the period it is: its first day until the first of the next.
    await waitFor(() => {
      const asked = calls.filter((call) => call.path === '/api/v1/search').at(-1)
      expect(asked?.body).toMatchObject({ date_from: '2012-01-01', date_until: '2013-01-01' })
    })
    // The chip says which year, with a way to take it off again.
    expect(await screen.findByRole('button', { name: '2012' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Jahr nicht mehr einschränken' }),
    ).toBeInTheDocument()
  })

  it('says up front what a search without a picture model can find, and after a search too', async () => {
    stubApi({
      [ABILITIES]: { body: { pictures: false, meanings: false, ready: false } },
      [SEARCH]: { body: aPage([{ media: aMedium('italien') }]) },
    })

    const empty = await renderScreen(<SearchScreen />)
    expect(await screen.findByText(/Suche nach Alben- und Dateinamen/)).toBeInTheDocument()
    expect(screen.queryByText(/Beschreibe, was du suchst/)).not.toBeInTheDocument()
    empty.unmount()

    await renderScreen(<SearchScreen q="Italien" />)
    expect(await screen.findByText(/Ohne Bildmodell/)).toBeInTheDocument()
  })

  it.each([
    [true, 1],
    [false, 0],
  ])('offers pictures like this one only with a picture model (%s)', async (pictures, buttons) => {
    stubApi({
      [ABILITIES]: { body: { pictures, meanings: true, ready: true } },
      [SEARCH]: { body: aPage([{ media: aMedium('strand') }]) },
    })

    await renderScreen(<SearchScreen q="Strand" medium="strand" />, { path: '/search' })

    expect(await screen.findByRole('button', { name: 'Details anzeigen' })).toBeInTheDocument()
    expect(screen.queryAllByRole('button', { name: 'Ähnliche Bilder' })).toHaveLength(buttons)
  })

  it('shows what was found, and where in a video it was', async () => {
    const { calls } = stubApi({
      [SEARCH]: {
        body: aPage([
          { media: aMedium('strand') },
          { media: aMedium('film', 'video'), moment: 83.4 },
        ]),
      },
    })

    await renderScreen(<SearchScreen q="Strand" kind="video" />)

    // The region is named the same while it waits, so the tiles are what to wait for.
    await screen.findAllByRole('button', { name: /Medium vom/ })
    const results = screen.getByRole('region', { name: 'Suchergebnisse' })
    expect(within(results).getAllByRole('button', { name: /Medium vom/ })).toHaveLength(2)
    expect(within(results).getByText('bei 1:23')).toBeInTheDocument()
    expect(calls.find((call) => call.method === 'POST')?.body).toMatchObject({
      q: 'Strand',
      kind: 'video',
      sort: 'relevance',
    })
    // The dropdown carries the chosen kind rather than three chips side by side.
    expect(screen.getByText('Videos')).toBeInTheDocument()
  })

  it('shows the period it read out of the words', async () => {
    stubApi({
      [SEARCH]: {
        body: aPage([{ media: aMedium('strand') }], {
          understood: {
            text: 'Strand',
            date_from: '2012-06-01',
            date_until: '2012-09-01',
            kind: null,
          },
        }),
      },
    })

    await renderScreen(<SearchScreen q="Strand im Sommer 2012" />)

    expect(await screen.findByText('Juni – August 2012')).toBeInTheDocument()
  })

  it('says so when the pictures themselves could not be asked', async () => {
    stubApi({ [SEARCH]: { body: aPage([{ media: aMedium('strand') }], { degraded: true }) } })

    await renderScreen(<SearchScreen q="Strand" />)

    expect(await screen.findByText(/KI-Server antwortet gerade nicht/)).toBeInTheDocument()
  })

  it('says so when nothing was found', async () => {
    stubApi({ [SEARCH]: { body: aPage([]) } })

    await renderScreen(<SearchScreen q="Einhorn" />)

    expect(await screen.findByText(/Nichts gefunden/)).toBeInTheDocument()
  })

  it('shows pictures like a given one', async () => {
    stubApi({
      'GET /api/v1/media/strand/similar': { body: aPage([{ media: aMedium('meer') }]) },
    })

    await renderScreen(<SearchScreen similar="strand" />)

    expect(await screen.findByRole('heading', { name: 'Ähnliche Bilder' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Medium vom/ })).toBeInTheDocument()
  })
})

describe('the period in words', () => {
  const t = ((key: string, values: { from: string; until: string }) =>
    key === 'search.period' ? `${values.from} – ${values.until}` : key) as never

  it.each([
    ['2012-01-01', '2013-01-01', '2012'],
    ['2010-01-01', '2015-01-01', '2010 – 2014'],
    ['2014-07-01', '2014-08-01', 'Juli 2014'],
    ['2012-06-01', '2012-09-01', 'Juni – August 2012'],
    ['2010-12-01', '2011-03-01', 'Dezember 2010 – Februar 2011'],
  ])('%s to %s is %s', (from, until, said) => {
    expect(period(from, until, t)).toBe(said)
  })
})
