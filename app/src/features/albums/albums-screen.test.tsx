import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AlbumsScreen } from '@/features/albums/albums-screen'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const TREE = 'GET /api/v1/albums/tree'
const MEDIA = 'GET /api/v1/albums/album-italien/media'
const SYNC = 'POST /api/v1/albums/album-italien/sync'

function anAlbum(overrides: Record<string, unknown>) {
  return {
    id: 'album-root',
    parent_id: null,
    relative_path: '',
    is_source: true,
    name: 'Fotos',
    title: 'Fotos',
    custom_title: null,
    description: null,
    media_count: 0,
    child_count: 1,
    cover_urls: [],
    created_at: '2026-09-19T10:00:00Z',
    last_sync_at: '2026-09-20T08:00:00Z',
    last_sync_status: 'ok' as const,
    last_sync_message: null,
    ...overrides,
  }
}

const root = anAlbum({})
const italien = anAlbum({
  id: 'album-italien',
  parent_id: 'album-root',
  relative_path: '2009 Italien',
  name: '2009 Italien',
  title: 'Italien mit Oma',
  media_count: 2,
  child_count: 0,
  cover_urls: ['/api/v1/media/media-1/thumb?token=abc'],
})

function aMedium(overrides: Record<string, unknown>) {
  return {
    id: 'media-1',
    album_id: 'album-italien',
    kind: 'image' as const,
    status: 'active' as const,
    taken_at: '2009-07-14T15:30:12Z',
    taken_at_source: 'exif' as const,
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: null,
    camera_make: 'Canon',
    camera_model: 'EOS 400D',
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      root_id: 'root-1',
      root_name: 'Fotos',
      relative_path: '2009 Italien/IMG_1.jpg',
      filename: 'IMG_1.jpg',
      byte_size: 30801,
    },
    urls: {
      thumb: '/api/v1/media/media-1/thumb?token=abc',
      preview: '/api/v1/media/media-1/preview?token=abc',
      video: null,
      poster: null,
      original: '/api/v1/media/media-1/original?token=abc',
    },
    files: [],
    ...overrides,
  }
}

beforeEach(() => {
  useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the album tree', () => {
  it('shows the roots of the library', async () => {
    stubApi({ [TREE]: { body: { items: [root, italien] } } })

    await renderScreen(<AlbumsScreen />)

    expect(await screen.findByText('Fotos')).toBeInTheDocument()
    expect(screen.getByText('1 Unteralbum')).toBeInTheDocument()
    // Only the top level; the album inside it belongs to its own page.
    expect(screen.queryByText('Italien mit Oma')).not.toBeInTheDocument()
  })

  it('says what belongs here while nothing is published', async () => {
    useAuthStore.setState({
      status: 'signed-in',
      user: { ...aUser, role: 'admin' },
      needsPasswordChange: false,
    })
    stubApi({ [TREE]: { body: { items: [] } } })

    await renderScreen(<AlbumsScreen />)

    expect(await screen.findByText('Hier entstehen deine Alben')).toBeInTheDocument()
    // Publishing belongs to the admin area, for an admin as much as for anybody else.
    expect(screen.queryByRole('link', { name: /veröffentlichen/ })).not.toBeInTheDocument()
  })

  it('names the tiles for the level one is on', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [], next_cursor: null, prev_cursor: null } },
    })

    const { unmount } = await renderScreen(<AlbumsScreen />)
    // At the root the tiles are albums; inside one they are its subalbums.
    expect(await screen.findByRole('region', { name: 'Alben' })).toBeInTheDocument()
    unmount()

    await renderScreen(<AlbumsScreen albumId="album-root" />)
    expect(await screen.findByRole('region', { name: 'Unteralben' })).toBeInTheDocument()
  })

  it('claims nothing about an album while the tree is on its way', async () => {
    // Before the tree lands the page used to call every album "Alben" and say it held none,
    // and then take both back. Now it holds the same shape and says nothing.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    )

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    expect(screen.queryByRole('heading', { name: 'Alben' })).not.toBeInTheDocument()
    expect(screen.queryByText('0 Alben')).not.toBeInTheDocument()
    // The shell brings a header of its own, so it is the album's that has to say it is busy.
    expect(document.querySelector('header[aria-busy="true"]')).not.toBeNull()
    expect(screen.getAllByText('Wird geladen …').length).toBeGreaterThan(0)
  })

  it('keeps the header the same shape with and without a sync button', async () => {
    stubApi({
      // A folder inside a published one: it is synced with its parent, so it has no button.
      [TREE]: { body: { items: [root, { ...italien, is_source: false }] } },
      [MEDIA]: { body: { items: [], next_cursor: null, prev_cursor: null } },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    // Italien is no published folder of its own, so it has no button - but the lane that would
    // hold one is there all the same, which is what keeps the tiles below from moving.
    await screen.findByRole('heading', { name: 'Italien mit Oma' })
    expect(screen.queryByRole('button', { name: 'Jetzt abgleichen' })).not.toBeInTheDocument()
    const lane = document.querySelector('header > div > div:last-child')
    expect(lane).toHaveClass('h-11')
  })

  it('folds the middle of a long path on a narrow screen', async () => {
    // Fotos > 2009 > Italien > Rom: four steps below "Alben", one more than a phone shows.
    const jahr = anAlbum({ id: 'album-2009', parent_id: 'album-root', title: '2009' })
    const rom = anAlbum({ id: 'album-rom', parent_id: 'album-italien', title: 'Rom' })
    stubApi({
      [TREE]: { body: { items: [root, jahr, { ...italien, parent_id: 'album-2009' }, rom] } },
      'GET /api/v1/albums/album-rom/media': {
        body: { items: [], next_cursor: null, prev_cursor: null },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-rom" />)

    await screen.findByRole('heading', { name: 'Rom' })
    const path = screen.getByRole('navigation', { name: 'Pfad im Albenbaum' })
    // "Alben … Italien mit Oma > Rom" - and the "…" still leads one level up.
    expect(
      within(path).getByRole('link', { name: 'Übergeordnete Alben, zu 2009' }),
    ).toHaveAttribute('href', '/albums/album-2009')
    expect(within(path).getByRole('link', { name: 'Italien mit Oma' })).toBeInTheDocument()
    expect(within(path).getByText('Rom')).toBeInTheDocument()
    expect(within(path).queryByText('Fotos')).not.toBeInTheDocument()
    expect(within(path).queryByText('2009')).not.toBeInTheDocument()
  })

  it('says plainly when an album itself holds nothing', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [], next_cursor: null, prev_cursor: null } },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    expect(await screen.findByText('Dieses Album ist noch leer')).toBeInTheDocument()
  })

  it('fetches a picture the loaded page does not hold, so the viewer has one to show', async () => {
    // A link from elsewhere - the engine room naming the file it has just finished - can point
    // deep into an album of thousands. The viewer is built from the page that is loaded, so
    // there was nothing to open and the click did nothing at all.
    const { calls } = stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [aMedium({})], next_cursor: 'seite-2' } },
      'GET /api/v1/media/media-weit-hinten': {
        body: aMedium({ id: 'media-weit-hinten', taken_at: '2009-07-20T10:00:00Z' }),
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" medium="media-weit-hinten" />)

    await waitFor(() => {
      expect(calls.some((call) => call.path === '/api/v1/media/media-weit-hinten')).toBe(true)
    })
  })

  it('asks for nothing extra when the picture is already on the page', async () => {
    const { calls } = stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [aMedium({})], next_cursor: null } },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" medium="media-1" />)

    await screen.findByRole('link', { name: 'Fotos' })
    expect(calls.some((call) => call.path === '/api/v1/media/media-1')).toBe(false)
  })

  it('opens an album with its path, its pictures and its own title', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: {
        body: {
          items: [aMedium({}), aMedium({ id: 'media-2', taken_at: '2009-07-15T10:15:00Z' })],
          next_cursor: null,
        },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    expect(await screen.findByRole('link', { name: 'Fotos' })).toHaveAttribute(
      'href',
      '/albums/album-root',
    )
    expect(screen.getByRole('navigation', { name: 'Pfad im Albenbaum' })).toBeInTheDocument()
    expect(await screen.findAllByRole('button', { name: /Medium vom/ })).toHaveLength(2)
    expect(screen.getByText('2 Medien')).toBeInTheDocument()
  })

  it('shows a collage on a folder that only holds folders', async () => {
    const parent = anAlbum({
      cover_urls: ['/thumb/1', '/thumb/2', '/thumb/3', '/thumb/4'],
    })
    stubApi({ [TREE]: { body: { items: [parent, { ...italien, parent_id: 'album-root' }] } } })

    await renderScreen(<AlbumsScreen />)

    const tile = await screen.findByRole('link', { name: 'Album Fotos öffnen' })
    expect(within(tile).getAllByRole('presentation', { hidden: true })).toHaveLength(4)
  })

  it('pages through the album by way of the address', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: {
        body: { items: [aMedium({})], next_cursor: 'seite-2', prev_cursor: null },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    // The first page leads forwards only, and where it leads stands in the link.
    expect(await screen.findByRole('link', { name: /Weiter/ })).toHaveAttribute(
      'href',
      '/albums/album-italien?cursor=seite-2',
    )
    expect(screen.queryByRole('link', { name: /Zurück/ })).not.toBeInTheDocument()
  })

  it('opens the page a link was sent for, and leads back from it', async () => {
    const { calls } = stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: {
        body: { items: [aMedium({})], next_cursor: null, prev_cursor: 'seite-1' },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" cursor="seite-2" />)

    expect(await screen.findByRole('link', { name: /Zurück/ })).toHaveAttribute(
      'href',
      '/albums/album-italien?before=seite-1',
    )
    expect(screen.queryByRole('link', { name: /Weiter/ })).not.toBeInTheDocument()
    expect(calls.some((call) => call.url.includes('cursor=seite-2'))).toBe(true)
  })

  it('marks a video and an estimated date on the tile', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: {
        body: {
          items: [
            aMedium({
              id: 'media-3',
              kind: 'video',
              duration_seconds: 95,
              date_is_estimated: true,
              urls: {
                thumb: '/api/v1/media/media-3/thumb?token=abc',
                preview: null,
                video: '/api/v1/media/media-3/video?token=abc',
                poster: '/api/v1/media/media-3/poster?token=abc',
                original: '/api/v1/media/media-3/original?token=abc',
              },
            }),
          ],
          next_cursor: null,
        },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    expect(await screen.findByText('1:35')).toBeInTheDocument()
    expect(screen.getByTitle('Datum geschätzt')).toBeInTheDocument()
  })

  it('shows a tile without a preview instead of an empty box', async () => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: {
        body: {
          items: [
            aMedium({
              id: 'media-4',
              has_previews: false,
              urls: {
                thumb: null,
                preview: null,
                video: null,
                poster: null,
                original: '/api/v1/media/media-4/original?token=abc',
              },
            }),
          ],
          next_cursor: null,
        },
      },
    })

    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    const tile = await screen.findByRole('button', { name: /Medium vom/ })
    expect(within(tile).queryByRole('img')).not.toBeInTheDocument()
  })

  it('lets anybody ask for a sync and shows what it found', async () => {
    const { calls } = stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [], next_cursor: null } },
      [SYNC]: {
        status: 202,
        body: { album_id: italien.id, job_id: 'job-1', task_id: 'task-1' },
      },
      'GET /api/v1/albums/album-italien/sync/job-1': {
        body: {
          job_id: 'job-1',
          state: 'done',
          updated_at: '2026-09-20T09:00:00Z',
          result: { added: 4, changed: 1, missing: 2, restored: 0, moved: 0 },
        },
      },
    })
    await renderScreen(<AlbumsScreen albumId="album-italien" />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Jetzt abgleichen' }))

    // Only what happened, nothing that stayed at zero.
    expect(await screen.findByRole('status')).toHaveTextContent('4 neu, 1 geändert, 2 entfernt')
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ with_children: true })
  })

  it.each([
    [{ added: 0, changed: 0, missing: 0, restored: 1, moved: 0 }, '1 zurückgekehrt'],
    [
      { added: 0, changed: 0, missing: 0, restored: 0, moved: 0, waiting: 1 },
      '1 wird gleich geprüft',
    ],
    [{ added: 0, changed: 0, missing: 0, restored: 0, moved: 0, waiting: 0 }, 'Keine Änderungen'],
  ])('names a file that came back, and says so when nothing changed', async (result, said) => {
    stubApi({
      [TREE]: { body: { items: [root, italien] } },
      [MEDIA]: { body: { items: [], next_cursor: null } },
      [SYNC]: {
        status: 202,
        body: { album_id: italien.id, job_id: 'job-1', task_id: 'task-1' },
      },
      'GET /api/v1/albums/album-italien/sync/job-1': {
        body: { job_id: 'job-1', state: 'done', updated_at: '2026-09-20T09:00:00Z', result },
      },
    })
    await renderScreen(<AlbumsScreen albumId="album-italien" />)

    await userEvent.click(await screen.findByRole('button', { name: 'Jetzt abgleichen' }))

    expect(await screen.findByRole('status')).toHaveTextContent(said)
  })
})
