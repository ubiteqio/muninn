import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { rememberTokens } from '@/api/session'
import { AdminJobsPage } from '@/features/admin/jobs-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const JOBS = 'GET /api/v1/admin/jobs'
const CHANGES = 'GET /api/v1/admin/index/changes'
const AI = 'GET /api/v1/admin/jobs/ai'

/** One AI machine, as the engine room hears about it. */
function aMachine(kind: string, ok: boolean) {
  return {
    kind,
    configured: true,
    model: 'buffalo_l',
    ok,
    detail: ok ? 'antwortet' : 'Keine Antwort',
    milliseconds: null,
    checked_at: '2026-09-26T20:00:00Z',
    paused_until: ok ? null : '2026-09-26T20:05:00Z',
  }
}

const idle = {
  running: [],
  active: [],
  last_read_at: null,
  albums: 0,
  media: 0,
  queues: [
    { name: 'scan', waiting: 0 },
    { name: 'derive', waiting: 0 },
    { name: 'ai', waiting: 0 },
  ],
  pending_metadata: 0,
  pending_derivatives: 0,
  pending_image_vectors: null,
  pending_transcripts: null,
  pending_analyses: null,
  pending_caption_vectors: null,
  waiting_files: 0,
  finished: [],
  done_last_minute: {
    metadata: 0,
    derive: 0,
    image_vector: 0,
    transcription: 0,
    analysis: 0,
    caption_vector: 0,
  },
  schedule: {
    next_quick_sync_at: null,
    next_full_sync_at: null,
    quick_sync_seconds: 300,
    full_sync_hour: 3,
    stability_seconds: 30,
  },
}

/** A WebSocket the test can push messages into. */
class FakeSocket extends EventTarget {
  static readonly OPEN = 1
  readyState = FakeSocket.OPEN

  readonly url: string
  readonly protocols: string[] | undefined

  constructor(url: string, protocols?: string[]) {
    super()
    this.url = url
    this.protocols = protocols
    queueMicrotask(() => {
      this.dispatchEvent(new Event('open'))
    })
  }

  receive(event: unknown): void {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  }

  close(): void {
    this.dispatchEvent(new Event('close'))
  }

  send(): void {}
}

beforeEach(() => {
  useAuthStore.setState({
    status: 'signed-in',
    user: { ...aUser, role: 'admin' },
    needsPasswordChange: false,
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('work that waits for a machine', () => {
  it('says so on the line, instead of looking stuck', async () => {
    stubApi({
      [JOBS]: { body: { ...idle, pending_faces: 1 } },
      [CHANGES]: { body: [] },
      [AI]: { body: { services: [aMachine('face_detector', false)] } },
    })

    await renderScreen(<AdminJobsPage />)

    const row = await screen.findByText(/Medien ohne Gesichtersuche/)
    expect(row).toHaveTextContent('wartet auf die KI-Maschine')
  })

  it('says nothing of the sort while the machine answers', async () => {
    stubApi({
      [JOBS]: { body: { ...idle, pending_faces: 1 } },
      [CHANGES]: { body: [] },
      [AI]: { body: { services: [aMachine('face_detector', true)] } },
    })

    await renderScreen(<AdminJobsPage />)

    const row = await screen.findByText(/Medien ohne Gesichtersuche/)
    expect(row).not.toHaveTextContent('wartet auf die KI-Maschine')
  })
})

describe('the engine room', () => {
  it('takes a hint from the live channel instead of waiting for the next question', async () => {
    // One socket per tab: the test holds on to it to play the server.
    const sockets: FakeSocket[] = []
    vi.stubGlobal(
      'WebSocket',
      class extends FakeSocket {
        constructor(url: string, protocols?: string[]) {
          super(url, protocols)
          sockets.push(this)
        }
      },
    )
    const { calls } = stubApi({ [JOBS]: { body: idle }, [CHANGES]: { body: [] } })
    // The socket carries the access token, so there has to be one.
    await rememberTokens({ accessToken: 'access-token-1' })
    await renderScreen(<AdminJobsPage />)
    await screen.findByText('Nichts in Arbeit.')
    const asked = calls.filter((call) => call.path === '/api/v1/admin/jobs').length

    // A burst of events, as a worker going through media produces it.
    for (let index = 0; index < 20; index += 1) {
      sockets[0]?.receive({ topic: 'jobs', kind: 'task_finished', stage: 'derive' })
    }

    await waitFor(() => {
      expect(calls.filter((call) => call.path === '/api/v1/admin/jobs').length).toBe(asked + 1)
    })
    // The token travels as a subprotocol, never in the address.
    expect(sockets[0]?.protocols?.[0]).toBe('bearer')
    expect(sockets[0]?.url).not.toContain('token')
  })

  it('names the media behind a number, and what stopped them', async () => {
    // A number can only be watched; a list can be acted on. Until now the reason lived in a
    // worker's log and only if something had crashed loudly enough to print it.
    stubApi({
      [JOBS]: { body: { ...idle, pending_derivatives: 2 } },
      [CHANGES]: { body: [] },
      'GET /api/v1/admin/jobs/waiting/derive': {
        body: {
          stage: 'derive',
          files: [],
          items: [
            {
              media_id: 'm1',
              kind: 'video',
              filename: 'VIDEO0001.3gp',
              album: 'Kinder/2010',
              album_id: 'a1',
              byte_size: 41_943_040,
              attempts: 3,
              last_at: new Date().toISOString(),
              last_error: "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xfe",
            },
          ],
        },
      },
    })

    await renderScreen(<AdminJobsPage />)

    const line = await screen.findByRole('button', { name: /Medien ohne Vorschau/ })
    expect(line).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(line)

    expect(await screen.findByText('VIDEO0001.3gp')).toBeInTheDocument()
    expect(screen.getByText(/Kinder\/2010/)).toBeInTheDocument()
    expect(screen.getByText(/3 Versuche/)).toBeInTheDocument()
    expect(screen.getByText(/41,9 MB/)).toBeInTheDocument()
    expect(screen.getByText(/UnicodeDecodeError/)).toBeInTheDocument()
    expect(line).toHaveAttribute('aria-expanded', 'true')
  })

  it('asks nothing until a number is opened', async () => {
    const { calls } = stubApi({
      [JOBS]: { body: { ...idle, pending_derivatives: 2 } },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)
    await screen.findByRole('button', { name: /Medien ohne Vorschau/ })

    expect(calls.some((call) => call.path.includes('/waiting/'))).toBe(false)
  })

  it('names the files it had to walk past, and why', async () => {
    // Nothing clears these by itself: somebody has to give Muninn leave to read them.
    stubApi({
      [JOBS]: { body: { ...idle, unreadable_files: 1 } },
      [CHANGES]: { body: [] },
      'GET /api/v1/admin/jobs/waiting/unreadable': {
        body: {
          stage: 'unreadable',
          items: [],
          files: [
            {
              relative_path: 'Kinder/2019/IMG_3829.MOV',
              first_seen_at: new Date().toISOString(),
              byte_size: 419_396_824,
              reason: "[Errno 13] Permission denied: '/library/Kinder/2019/IMG_3829.MOV'",
            },
          ],
        },
      },
    })

    await renderScreen(<AdminJobsPage />)

    await userEvent.click(
      await screen.findByRole('button', { name: /nicht gelesen werden konnten/ }),
    )

    expect(await screen.findByText('Kinder/2019/IMG_3829.MOV')).toBeInTheDocument()
    expect(screen.getByText(/Permission denied/)).toBeInTheDocument()
  })

  it('says when there is nothing to do', async () => {
    stubApi({ [JOBS]: { body: idle }, [CHANGES]: { body: [] } })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText('Nichts in Arbeit.')).toBeInTheDocument()
    expect(screen.getByText(/Noch nie gelesen/)).toBeInTheDocument()
    expect(screen.getByText('Noch nichts gefunden.')).toBeInTheDocument()
  })

  it('says what just happened when nothing is running', async () => {
    const justFinished = new Date(Date.now() - 2 * 60_000).toISOString()
    stubApi({
      [JOBS]: {
        body: { ...idle, last_read_at: justFinished, media: 8, albums: 2, photos: 6, videos: 2 },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(
      await screen.findByText(/Zuletzt gelesen vor 2 Minuten · 8 Medien in 2 Alben/),
    ).toBeInTheDocument()
    // What the work is made of: a film is a transcode, a transcript and a description of
    // every fifth second; a photograph is none of that.
    expect(screen.getByText(/\(Bilder: 6, Videos: 2\)/)).toBeInTheDocument()
  })

  it('shows a running read with how far it got', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          running: [
            {
              publication_id: 'pub-1',
              relative_path: 'Autos/Captiva',
              name: 'Captiva',
              progress: { files_total: 684, files_done: 120, current: 'Autos/Captiva/Tag 1' },
            },
          ],
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText('Captiva')).toBeInTheDocument()
    expect(screen.getByText('120 von 684 Dateien')).toBeInTheDocument()
    // Counted in files: 120 of 684 is 18 percent, whatever the folders look like.
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '18')
  })

  it('shows the single media a worker has in its hands', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          active: [
            {
              task_id: 'task-1',
              stage: 'derive',
              label: 'IMG_0831.HEIC',
              started_at: new Date(Date.now() - 3000).toISOString(),
            },
          ],
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText('Vorschau wird erzeugt')).toBeInTheDocument()
    expect(screen.getByText('IMG_0831.HEIC')).toBeInTheDocument()
    expect(screen.getByText(/seit 3 s/)).toBeInTheDocument()
  })

  it('shows work that was over before anybody could look', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          // Nothing in hand: a preview takes about a tenth of a second, the page asks every two.
          finished: [
            {
              stage: 'derive',
              label: 'DSC01154.jpg',
              finished_at: new Date(Date.now() - 2000).toISOString(),
            },
          ],
          done_last_minute: { metadata: 312, derive: 170 },
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    const stream = within(await screen.findByRole('region', { name: 'Gerade fertig geworden' }))
    expect(stream.getByText('Vorschau erzeugt')).toBeInTheDocument()
    expect(stream.getByText('DSC01154.jpg')).toBeInTheDocument()
    expect(stream.getByText(/vor 2 s/)).toBeInTheDocument()
    expect(stream.getByText(/312 Medien gelesen · 170 Vorschauen/)).toBeInTheDocument()
    // Finished work is not running work: the state says plainly that nothing is in hand.
    expect(screen.getByText('Nichts in Arbeit.')).toBeInTheDocument()
  })

  it('lets the stream go once the work has gone cold', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          finished: [
            {
              stage: 'derive',
              label: 'DSC01154.jpg',
              finished_at: new Date(Date.now() - 10 * 60_000).toISOString(),
            },
          ],
          done_last_minute: { metadata: 0, derive: 0 },
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    await screen.findByText('Nichts in Arbeit.')
    // Ten minutes old is not "just finished"; what happened that long ago is in the log below.
    expect(screen.queryByRole('region', { name: 'Gerade fertig geworden' })).not.toBeInTheDocument()
  })

  it('stops one piece of work on request', async () => {
    const { calls } = stubApi({
      [JOBS]: {
        body: {
          ...idle,
          active: [
            {
              task_id: 'task-1',
              stage: 'derive',
              label: 'IMG_0831.HEIC',
              started_at: new Date().toISOString(),
            },
          ],
        },
      },
      [CHANGES]: { body: [] },
      'DELETE /api/v1/admin/jobs/active/task-1': { status: 202 },
    })
    await renderScreen(<AdminJobsPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Stoppen' }))

    expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
  })

  it('stops a running read between folders', async () => {
    const { calls } = stubApi({
      [JOBS]: {
        body: {
          ...idle,
          running: [
            {
              publication_id: 'pub-1',
              relative_path: 'Autos/Captiva',
              name: 'Captiva',
              progress: null,
            },
          ],
        },
      },
      [CHANGES]: { body: [] },
      'DELETE /api/v1/admin/jobs/reads/pub-1': { status: 202 },
    })
    await renderScreen(<AdminJobsPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Lesen abbrechen' }))

    expect(calls.some((call) => call.path === '/api/v1/admin/jobs/reads/pub-1')).toBe(true)
  })

  it('empties a queue, but asks first', async () => {
    const { calls } = stubApi({
      [JOBS]: {
        body: {
          ...idle,
          queues: [
            { name: 'scan', waiting: 0 },
            { name: 'derive', waiting: 1086 },
          ],
        },
      },
      [CHANGES]: { body: [] },
      'DELETE /api/v1/admin/jobs/queues/derive': { body: { name: 'derive', removed: 1086 } },
    })
    await renderScreen(<AdminJobsPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Leeren' }))
    const asked = await screen.findByRole('dialog')
    expect(within(asked).getByText(/Vorschauen.+wirklich leeren/)).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await user.click(within(asked).getByRole('button', { name: 'Leeren' }))
    expect(calls.some((call) => call.path === '/api/v1/admin/jobs/queues/derive')).toBe(true)
  })

  it('tells the work that is owed apart from the queues that carry it', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          queues: [
            { name: 'scan', waiting: 3 },
            { name: 'derive', waiting: 128 },
          ],
          waiting_files: 23,
          pending_derivatives: 128,
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    // Only what waits: the files to check and the previews, nothing that stands at zero.
    const owed = within(await screen.findByRole('region', { name: 'Was noch aussteht' }))
    expect(owed.getByText('23')).toBeInTheDocument()
    expect(owed.getByText('Dateien warten auf die zweite Prüfung')).toBeInTheDocument()
    expect(owed.getByText('Medien ohne Vorschau')).toBeInTheDocument()
    expect(owed.queryByText('Medien ohne Metadaten')).not.toBeInTheDocument()
    // The broker's queues stand apart, and say so in words rather than as a headline number.
    expect(owed.getByText(/In der Warteschlange/)).toBeInTheDocument()
    expect(screen.getByText(/Kein Durchgang läuft/)).toBeInTheDocument()
  })

  it('says in one line that nothing waits', async () => {
    stubApi({
      [JOBS]: { body: { ...idle, pending_image_vectors: 0, pending_analyses: 0 } },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    const owed = within(await screen.findByRole('region', { name: 'Was noch aussteht' }))
    expect(owed.getByText('Alles erledigt, nichts wartet.')).toBeInTheDocument()
    expect(owed.queryByText(/In der Warteschlange/)).not.toBeInTheDocument()
  })

  it('adds the AI stages to the way once their models are set up', async () => {
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          pending_image_vectors: 87,
          pending_transcripts: 3,
          pending_analyses: 64,
          pending_caption_vectors: 5,
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    const owed = within(await screen.findByRole('region', { name: 'Was noch aussteht' }))
    expect(owed.getByText('87')).toBeInTheDocument()
    expect(owed.getByText('Medien ohne Bildvektor')).toBeInTheDocument()
    expect(owed.getByText('64')).toBeInTheDocument()
    expect(owed.getByText('Videos ohne Transkript')).toBeInTheDocument()
    expect(owed.getByText('Medien ohne Beschreibung')).toBeInTheDocument()
    expect(owed.getByText('Beschreibungen ohne Textvektor')).toBeInTheDocument()
  })

  it('says "every minute" rather than "every 1 minutes"', async () => {
    stubApi({
      [JOBS]: { body: { ...idle, schedule: { ...idle.schedule, quick_sync_seconds: 60 } } },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText(/Schnell-Abgleich jede Minute/)).toBeInTheDocument()
  })

  it('says when the next read is due where the state is, and keeps the plan below', async () => {
    const soon = new Date(Date.now() + 4 * 60_000).toISOString()
    stubApi({
      [JOBS]: {
        body: { ...idle, schedule: { ...idle.schedule, next_quick_sync_at: soon } },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    const state = within(await screen.findByRole('region', { name: 'Stand' }))
    expect(state.getByText(/nächster Durchgang in etwa 4 Minuten/)).toBeInTheDocument()
    expect(screen.getByText(/täglich um 3 Uhr/)).toBeInTheDocument()
  })

  it('says a read due within the minute is about to start', async () => {
    const now = new Date(Date.now() + 20_000).toISOString()
    stubApi({
      [JOBS]: { body: { ...idle, schedule: { ...idle.schedule, next_quick_sync_at: now } } },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    const state = within(await screen.findByRole('region', { name: 'Stand' }))
    expect(state.getByText(/nächster Durchgang läuft gleich an/)).toBeInTheDocument()
  })

  it('says a read that just finished is over, not about to start', async () => {
    stubApi({
      [JOBS]: { body: { ...idle, last_read_at: new Date(Date.now() - 20_000).toISOString() } },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText(/Zuletzt gelesen gerade eben/)).toBeInTheDocument()
  })

  it('makes one line of findings of the same kind', async () => {
    stubApi({
      [JOBS]: { body: idle },
      [CHANGES]: {
        body: ['Autos/Yaris', 'Autos/Orlando', 'Autos/Daimler'].map((path, index) => ({
          id: `change-${String(index)}`,
          occurred_at: '2026-09-20T19:14:33Z',
          album_id: 'album-1',
          media_id: null,
          kind: 'album_added',
          trigger: 'clock',
          path,
        })),
      },
    })

    await renderScreen(<AdminJobsPage />)

    const rows = await screen.findAllByText('Album angelegt')
    expect(rows).toHaveLength(1)
    expect(screen.getByText('· 2 weitere')).toBeInTheDocument()
    expect(screen.getByText('Autos/Yaris')).toBeInTheDocument()
  })

  it('lists what the syncs found', async () => {
    stubApi({
      [JOBS]: { body: idle },
      [CHANGES]: {
        body: [
          {
            id: 'change-1',
            occurred_at: '2026-09-20T19:14:33Z',
            album_id: 'album-1',
            media_id: 'media-1',
            kind: 'media_added',
            trigger: 'manual',
            path: 'Autos/Captiva/DSC_0024.JPG',
          },
        ],
      },
    })

    await renderScreen(<AdminJobsPage />)

    const row = within(
      await screen
        .findByText('Autos/Captiva/DSC_0024.JPG')
        .then((node) => node.closest('li') as HTMLElement),
    )
    expect(row.getByText('Medium gefunden')).toBeInTheDocument()
  })

  it('keeps a plain user out', async () => {
    useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
    stubApi({})

    await renderScreen(<AdminJobsPage />)

    expect(screen.queryByRole('navigation', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('leads from a piece of work to the medium and its album, and names a failure', async () => {
    const media = {
      id: 'media-1',
      kind: 'video' as const,
      album_id: 'album-9',
      album_path: 'Events/2006-03-25 - Nuhr',
    }
    stubApi({
      [JOBS]: {
        body: {
          ...idle,
          active: [
            {
              task_id: 'task-1',
              stage: 'analysis',
              label: 'IMG_8334.MOV',
              started_at: new Date().toISOString(),
              media,
            },
          ],
          finished: [
            {
              stage: 'analysis',
              label: 'IMG_8333.MOV',
              finished_at: new Date().toISOString(),
              failed: true,
              media,
            },
          ],
        },
      },
      [CHANGES]: { body: [] },
    })

    await renderScreen(<AdminJobsPage />)

    expect(await screen.findByText('Video wird beschrieben')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'IMG_8334.MOV' })).toHaveAttribute(
      'href',
      '/albums/album-9?medium=media-1',
    )
    expect(screen.getAllByRole('link', { name: /Events\/2006-03-25 - Nuhr/ })[0]).toHaveAttribute(
      'href',
      '/albums/album-9',
    )
    expect(screen.getByText('Nicht beschrieben')).toBeInTheDocument()
  })
})
