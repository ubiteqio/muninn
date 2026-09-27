import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { PhotobooksPage } from '@/features/admin/photobooks-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const SHELF = 'GET /api/v1/photobooks'
const TREE = 'GET /api/v1/albums/tree'
const MAKE = 'POST /api/v1/photobooks'
const REMOVE = 'DELETE /api/v1/photobooks/buch-1'

function anAlbum(over: Record<string, unknown> = {}) {
  return {
    id: 'album-1',
    parent_id: null,
    relative_path: 'Urlaub 2024 - Estland',
    is_source: true,
    name: 'Urlaub 2024 - Estland',
    title: 'Urlaub 2024 - Estland',
    custom_title: null,
    description: null,
    media_count: 64,
    child_count: 0,
    ...over,
  }
}

function aBook(over: Record<string, unknown> = {}) {
  return {
    id: 'buch-1',
    album_id: 'album-1',
    album: 'Urlaub 2024 - Estland',
    title: 'Estland',
    subtitle: '25. bis 28. April 2024',
    style: 'scrapbook',
    size: 'medium',
    state: 'ready',
    written: true,
    trouble: '',
    pages: 23,
    media: 48,
    cover: null,
    from_at: null,
    until_at: null,
    built_at: null,
    created_at: '2024-05-01T09:00:00Z',
    ...over,
  }
}

describe('Fotobücher im Admin-Bereich', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: { ...aUser, role: 'admin' } as never })
  })

  it('makes books of a published album with the size and the ceiling', async () => {
    const { calls } = stubApi({
      [TREE]: { body: { items: [anAlbum()] } },
      [SHELF]: { body: { items: [] } },
      [MAKE]: { status: 202, body: { items: [aBook(), aBook({ id: 'buch-2' })], job_id: 'job-1' } },
    })

    await renderScreen(<PhotobooksPage />, { path: '/admin/photobooks' })

    // The tree has to be in before the album can be chosen from it.
    await screen.findByRole('option', { name: /Urlaub 2024 - Estland/ })
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /^Album/ }), 'album-1')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /Umfang/ }), 'large')
    const ceiling = screen.getByRole('spinbutton', { name: /Höchstzahl Bilder/ })
    await userEvent.clear(ceiling)
    await userEvent.type(ceiling, '60')
    const count = screen.getByRole('spinbutton', { name: /Anzahl Bücher/ })
    await userEvent.clear(count)
    await userEvent.type(count, '2')

    await userEvent.click(screen.getByRole('button', { name: /Fotobuch erstellen/ }))

    await waitFor(() => {
      expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
    })
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      album_id: 'album-1',
      size: 'large',
      style: 'scrapbook',
      max_media: 60,
      count: 2,
      title: '',
    })
    expect(await screen.findByText(/2 Bücher in Arbeit/)).toBeInTheDocument()
  })

  it('will not make a book before an album is chosen', async () => {
    stubApi({ [TREE]: { body: { items: [anAlbum()] } }, [SHELF]: { body: { items: [] } } })

    await renderScreen(<PhotobooksPage />, { path: '/admin/photobooks' })

    expect(await screen.findByRole('button', { name: /Fotobuch erstellen/ })).toBeDisabled()
    expect(screen.getByText(/Bitte zuerst ein Album wählen/)).toBeInTheDocument()
  })

  it('says of a book whether the machine wrote its texts', async () => {
    stubApi({
      [TREE]: { body: { items: [anAlbum()] } },
      [SHELF]: { body: { items: [aBook({ written: false })] } },
    })

    await renderScreen(<PhotobooksPage />, { path: '/admin/photobooks' })

    expect(await screen.findByText(/ohne Texte/)).toBeInTheDocument()
    expect(screen.getByText(/23 Seiten · 48 Bilder/)).toBeInTheDocument()
  })

  it('asks before a book is removed, and removes it on yes', async () => {
    const { calls } = stubApi({
      [TREE]: { body: { items: [anAlbum()] } },
      [SHELF]: { body: { items: [aBook()] } },
      [REMOVE]: { status: 204 },
    })

    await renderScreen(<PhotobooksPage />, { path: '/admin/photobooks' })
    await userEvent.click(await screen.findByRole('button', { name: 'Löschen' }))

    // Nothing is gone yet: the trigger only opens the question.
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
    expect(await screen.findByText(/Fotobuch löschen\?/)).toBeInTheDocument()
    expect(screen.getByText(/Die Bilder im Album bleiben unberührt/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Löschen', hidden: false }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
    })
  })
})
