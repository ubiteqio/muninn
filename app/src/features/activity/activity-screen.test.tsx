import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ActivityScreen } from '@/features/activity/activity-screen'
import { ActivitySection } from '@/features/activity/activity-section'
import type { Happening } from '@/features/notify/use-notifications'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const ALBUM = { id: 'album-1', title: 'Sommer am See' }

function picture(id: string) {
  return {
    id,
    kind: 'image' as const,
    album_id: ALBUM.id,
    thumb: `/api/v1/media/${id}/thumb?token=t`,
    preview: `/api/v1/media/${id}/preview?token=t`,
  }
}

function happening(overrides: Partial<Happening> & Pick<Happening, 'key' | 'kind'>): Happening {
  return {
    actor: null,
    count: 1,
    at: new Date().toISOString(),
    media: null,
    album: ALBUM,
    excerpt: null,
    reaction: null,
    previews: [],
    ...overrides,
  }
}

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()

function yesterdayAtNoon(): string {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 12).toISOString()
}

const COMMENT = happening({
  key: 'comment:1',
  kind: 'comment',
  actor: 'Anna',
  at: minutesAgo(0),
  excerpt: 'Was für ein Abend!',
  media: picture('m-1'),
  previews: [picture('m-1')],
})

const BATCH = happening({
  key: 'new:album-1:1',
  kind: 'new_media',
  count: 7,
  at: yesterdayAtNoon(),
  media: picture('m-2'),
  previews: ['m-2', 'm-3', 'm-4', 'm-5'].map(picture),
})

describe('the news feed', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('hangs the posts on a timeline, one heading per day', async () => {
    stubApi({ 'GET /api/v1/activity': { body: { items: [COMMENT, BATCH], next_cursor: null } } })
    await renderScreen(<ActivityScreen />, { path: '/activity' })

    const today = await screen.findByRole('region', { name: 'Heute' })
    const yesterday = screen.getByRole('region', { name: 'Gestern' })

    expect(within(today).getByText('Was für ein Abend!')).toBeInTheDocument()
    expect(within(today).getByText('Anna')).toBeInTheDocument()
    expect(within(yesterday).getByText('7 neue Medien')).toBeInTheDocument()
  })

  it('shows the larger copy and leads to the picture in its album', async () => {
    stubApi({ 'GET /api/v1/activity': { body: { items: [COMMENT], next_cursor: null } } })
    await renderScreen(<ActivityScreen />, { path: '/activity' })

    const link = await screen.findByRole('link', { name: 'Bild im Album öffnen' })

    expect(link).toHaveAttribute('href', '/albums/album-1?medium=m-1')
    expect(link.querySelector('img')).toHaveAttribute('src', '/api/v1/media/m-1/preview?token=t')
  })

  it('shows a batch as a grid whose last tile counts the rest', async () => {
    stubApi({ 'GET /api/v1/activity': { body: { items: [BATCH], next_cursor: null } } })
    await renderScreen(<ActivityScreen />, { path: '/activity' })

    const tiles = await screen.findAllByRole('link', { name: /Bild im Album öffnen/ })

    expect(tiles).toHaveLength(4)
    expect(within(tiles[3] as HTMLElement).getByText('3 weitere im Album')).toBeInTheDocument()
  })

  it('asks for the next page as the end comes into view', async () => {
    // jsdom lays nothing out: this watcher says the end is in view the moment it is watched.
    class InView {
      private readonly report: IntersectionObserverCallback
      constructor(report: IntersectionObserverCallback) {
        this.report = report
      }
      observe() {
        this.report(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        )
      }
      disconnect() {}
    }
    vi.stubGlobal('IntersectionObserver', InView)
    const { calls } = stubApi({
      'GET /api/v1/activity': { body: { items: [COMMENT], next_cursor: BATCH.at } },
      [`GET /api/v1/activity?before=${encodeURIComponent(BATCH.at)}`]: {
        body: { items: [BATCH], next_cursor: null },
      },
    })
    await renderScreen(<ActivityScreen />, { path: '/activity' })

    expect(await screen.findByText('7 neue Medien')).toBeInTheDocument()
    await waitFor(() => {
      expect(calls.filter((call) => call.path === '/api/v1/activity')).toHaveLength(2)
    })
  })

  it('says so when nothing has happened yet', async () => {
    stubApi({ 'GET /api/v1/activity': { body: { items: [], next_cursor: null } } })
    await renderScreen(<ActivityScreen />, { path: '/activity' })

    expect(await screen.findByText(/Noch ist es still/)).toBeInTheDocument()
  })
})

describe('the news on the start page', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('leads to the whole feed', async () => {
    stubApi({ 'GET /api/v1/activity': { body: { items: [COMMENT], next_cursor: null } } })
    await renderScreen(<ActivitySection />)

    expect(screen.getByRole('link', { name: 'Alle ansehen' })).toHaveAttribute('href', '/activity')
  })
})
