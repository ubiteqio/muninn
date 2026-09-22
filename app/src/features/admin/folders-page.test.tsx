import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminFoldersPage } from '@/features/admin/folders-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const STATUS = 'GET /api/v1/admin/index/status'
const BROWSE = 'GET /api/v1/admin/library/browse'
const PUBLISH = 'POST /api/v1/admin/library/publications'
const SYNC = 'POST /api/v1/admin/library/publications/pub-1/sync'

const publication = {
  id: 'pub-1',
  relative_path: 'Urlaub/Brasilien',
  name: 'Brasilien',
  enabled: true,
  last_sync_at: '2026-09-20T08:00:00Z',
  last_sync_status: 'ok' as const,
  last_sync_message: null,
  pending_deletions: 0,
  created_at: '2026-09-19T10:00:00Z',
  progress: null,
  waiting_files: 0,
}

const status = {
  publications: [publication],
  library_path: '/library',
  next_sync_at: null,
  albums: 3,
  media: 128,
  missing: 0,
  pending_metadata: 0,
  pending_derivatives: 0,
}

const folders = {
  relative_path: '',
  library_path: '/library',
  current: {
    name: '',
    path: '/library',
    relative_path: '',
    is_mount: true,
    published: false,
    media_files: 0,
  },
  items: [
    {
      name: 'Urlaub',
      path: '/library/Urlaub',
      relative_path: 'Urlaub',
      is_mount: true,
      published: false,
      media_files: null,
    },
    {
      name: 'Fotos',
      path: '/library/Fotos',
      relative_path: 'Fotos',
      is_mount: false,
      published: true,
      media_files: null,
    },
  ],
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

/** The row of the folder picker that shows this folder. */
function rowFor(dialog: HTMLElement, name: string): HTMLElement {
  const row = within(dialog)
    .getAllByRole('listitem')
    .find((item) => within(item).queryByText(name) !== null)
  if (!row) throw new Error(`No row for ${name}`)
  return row
}

describe('the folders under Albums', () => {
  it('shows what is published and what came of it', async () => {
    stubApi({ [STATUS]: { body: status } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText('Brasilien')).toBeInTheDocument()
    expect(screen.getByText('Urlaub/Brasilien')).toBeInTheDocument()
    expect(screen.getByText('Gelesen')).toBeInTheDocument()
    expect(screen.getByText('128')).toBeInTheDocument()
  })

  it('shows how far a running read got', async () => {
    const running = {
      ...publication,
      last_sync_status: 'running' as const,
      progress: { files_total: 684, files_done: 320, current: 'Urlaub/Brasilien/Tag 2' },
    }
    stubApi({ [STATUS]: { body: { ...status, publications: [running] } } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText('320 von 684 Dateien')).toBeInTheDocument()
    expect(screen.getByText('Urlaub/Brasilien/Tag 2')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '320')
  })

  it('says when the clock reads again by itself', async () => {
    const soon = new Date(Date.now() + 4 * 60_000).toISOString()
    stubApi({ [STATUS]: { body: { ...status, next_sync_at: soon } } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText(/Nächster Lauf in etwa 4 Minuten/)).toBeInTheDocument()
  })

  it('says when files are still being copied, rather than just "read"', async () => {
    const waiting = { ...publication, waiting_files: 8 }
    stubApi({ [STATUS]: { body: { ...status, publications: [waiting], media: 0 } } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText(/8 Dateien werden noch geprüft/)).toBeInTheDocument()
  })

  it('says where the library is', async () => {
    stubApi({ [STATUS]: { body: status } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText(/Bibliothek ist \/library/)).toBeInTheDocument()
  })

  it('says so when nothing is published yet', async () => {
    stubApi({ [STATUS]: { body: { ...status, publications: [], albums: 0, media: 0 } } })

    await renderScreen(<AdminFoldersPage />)

    expect(await screen.findByText(/Noch kein Ordner veröffentlicht/)).toBeInTheDocument()
  })

  it('publishes a folder without asking for a name', async () => {
    const { calls } = stubApi({
      [STATUS]: { body: status },
      [BROWSE]: { body: folders },
      [PUBLISH]: { status: 201, body: { ...publication, id: 'pub-2' } },
    })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Ordner veröffentlichen' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByRole('listitem')
    await user.click(
      within(rowFor(dialog, 'Urlaub')).getByRole('button', { name: 'Veröffentlichen' }),
    )

    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ path: 'Urlaub' })
  })

  it('folds a deep path into the library, an ellipsis and the last two folders', async () => {
    const deep = {
      ...folders,
      items: [{ ...folders.items[0], name: '29', relative_path: '_mac/2017/01/29' }],
    }
    const { calls } = stubApi({ [STATUS]: { body: status }, [BROWSE]: { body: deep } })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Ordner veröffentlichen' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(await within(dialog).findByRole('button', { name: /^29/ }))

    const path = within(dialog).getByRole('navigation', { name: 'Pfad in der Bibliothek' })
    for (const step of ['/library', '…', '01', '29']) {
      expect(within(path).getByText(step)).toBeInTheDocument()
    }
    for (const step of ['_mac', '2017']) {
      expect(within(path).queryByText(step)).not.toBeInTheDocument()
    }

    await user.click(within(path).getByRole('button', { name: 'Übergeordnete Ordner, zu 2017' }))
    expect(new URL(calls.at(-1)?.url ?? '').searchParams.get('path')).toBe('_mac/2017')
  })

  it('offers the library itself, for pictures that lie in the mount', async () => {
    stubApi({ [STATUS]: { body: status }, [BROWSE]: { body: folders } })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Ordner veröffentlichen' }))
    const dialog = await screen.findByRole('dialog')

    expect(await within(dialog).findByText('Keine Medien direkt darin')).toBeInTheDocument()
  })

  it('does not offer a folder that is published already', async () => {
    stubApi({ [STATUS]: { body: status }, [BROWSE]: { body: folders } })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Ordner veröffentlichen' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByRole('listitem')
    expect(
      within(rowFor(dialog, 'Fotos')).getByRole('button', { name: 'Schon veröffentlicht' }),
    ).toBeDisabled()
    // A share the host mounted is highlighted, because that is usually what one is looking for.
    expect(within(rowFor(dialog, 'Urlaub')).getByText('Eingehängte Freigabe')).toBeInTheDocument()
  })

  it('reads a folder again on request', async () => {
    const { calls } = stubApi({
      [STATUS]: { body: status },
      [SYNC]: { status: 202, body: { publication_id: publication.id, task_id: 'task-1' } },
    })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Jetzt lesen' }))

    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      quick: false,
      confirm_deletions: false,
    })
  })

  it('asks for a confirmation when the sync paused on missing files', async () => {
    const paused = {
      ...publication,
      last_sync_status: 'paused' as const,
      pending_deletions: 42,
      last_sync_message: '42 of 100 files would be marked as missing.',
    }
    const { calls } = stubApi({
      [STATUS]: { body: { ...status, publications: [paused] } },
      [SYNC]: { status: 202, body: { publication_id: publication.id, task_id: 'task-2' } },
    })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    expect(await screen.findByText(/Angehalten/)).toBeInTheDocument()
    // The server's English sentence is not shown; the status line and the dialog say it.
    expect(screen.queryByText(/would be marked as missing/)).toBeNull()

    // The question is a dialog: the page button alone deletes nothing.
    await user.click(screen.getByRole('button', { name: '42 Löschungen bestätigen' }))
    const asked = await screen.findByRole('dialog')
    expect(within(asked).getByText('42 Dateien als fehlend markieren?')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)

    await user.click(within(asked).getByRole('button', { name: 'Als fehlend markieren' }))

    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      quick: false,
      confirm_deletions: true,
    })
  })

  it('takes a folder back out of the albums', async () => {
    const { calls } = stubApi({
      [STATUS]: { body: status },
      'DELETE /api/v1/admin/library/publications/pub-1': { status: 204 },
    })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    // The question is a dialog, never a second button in the page.
    await user.click(await screen.findByRole('button', { name: 'Nicht mehr veröffentlichen' }))
    const asked = await screen.findByRole('dialog')
    expect(within(asked).getByText(/Brasilien.+wirklich entfernen/)).toBeInTheDocument()

    await user.click(within(asked).getByRole('button', { name: 'Abbrechen' }))
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Nicht mehr veröffentlichen' }))
    const again = await screen.findByRole('dialog')
    await user.click(within(again).getByRole('button', { name: 'Wirklich entfernen' }))

    expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
  })

  it('says when the indexing is not running', async () => {
    stubApi({
      [STATUS]: { body: status },
      [SYNC]: {
        problem: {
          type: 'urn:muninn:problem:worker-unreachable',
          title: 'Worker unreachable',
          status: 503,
        },
      },
    })
    await renderScreen(<AdminFoldersPage />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Jetzt lesen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Die Indexierung läuft nicht')
  })

  it('keeps a plain user out', async () => {
    useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
    stubApi({})

    await renderScreen(<AdminFoldersPage />)

    expect(screen.queryByRole('navigation', { name: 'Admin' })).not.toBeInTheDocument()
  })
})
