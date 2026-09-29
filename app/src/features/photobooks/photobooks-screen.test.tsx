import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { BookReader, sideOf } from '@/features/photobooks/book-reader'
import { PhotobooksScreen } from '@/features/photobooks/photobooks-screen'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const SHELF = 'GET /api/v1/photobooks'
const BOOK = 'GET /api/v1/photobooks/buch-1'

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
    cover: '/api/v1/media/abc/thumb?token=xyz',
    from_at: '2024-04-25T10:00:00Z',
    until_at: '2024-04-28T09:00:00Z',
    built_at: '2024-05-01T10:00:00Z',
    created_at: '2024-05-01T09:00:00Z',
    ...over,
  }
}

function aPicture(id: string) {
  return {
    id,
    variant: 'preview',
    src: `/api/v1/media/${id}/preview?token=xyz`,
    tilt: 1.2,
    tape: 'washi',
    portrait: false,
    video: false,
    at: '10:32',
  }
}

const LEAVES = [
  {
    kind: 'auftakt',
    title: 'Estland',
    subtitle: '25. bis 28. April 2024',
    route: 'Pernau · Tallinn',
    counts: '48 Aufnahmen',
    hero: aPicture('bild-1'),
  },
  {
    kind: 'zwei',
    headline: 'Zusammen im Auto',
    note: '11:23 Uhr',
    story: 'Ein Moment, bevor es losgeht.',
    card: null,
    pictures: [
      { ...aPicture('bild-2'), caption: 'Lauri sitzt links im Auto' },
      { ...aPicture('bild-3'), caption: 'Matteo trägt Sonnenbrille' },
    ],
  },
  {
    kind: 'doppelseite',
    headline: 'Der Grill ist an',
    note: 'Tallinn · 15:56 Uhr',
    story: 'Boris wendet das Fleisch.',
    picture: aPicture('bild-4'),
  },
]

describe('Fotobücher', () => {
  beforeEach(() => {
    useAuthStore.setState({ status: 'signed-in', user: aUser, needsPasswordChange: false })
    // The book reader measures the window to decide whether two pages fit beside each other.
    vi.stubGlobal('innerWidth', 1440)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows the shelf with what each book holds', async () => {
    stubApi({ [SHELF]: { body: { items: [aBook()] } } })

    await renderScreen(<PhotobooksScreen />, { path: '/photobooks' })

    expect(await screen.findByText('Estland')).toBeInTheDocument()
    expect(screen.getByText(/25\. bis 28\. April 2024 · 23 Seiten/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Estland aufschlagen/ })).toHaveAttribute(
      'href',
      '/photobooks/buch-1',
    )
  })

  it('says that a book is still being built, and does not open it', async () => {
    stubApi({
      [SHELF]: { body: { items: [aBook({ state: 'building', pages: 0, cover: null })] } },
    })

    await renderScreen(<PhotobooksScreen />, { path: '/photobooks' })

    expect(await screen.findByText('wird gebaut')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /aufschlagen/ })).not.toBeInTheDocument()
  })

  it('says when there is no book yet', async () => {
    stubApi({ [SHELF]: { body: { items: [] } } })

    await renderScreen(<PhotobooksScreen />, { path: '/photobooks' })

    expect(await screen.findByText(/Noch kein Fotobuch/)).toBeInTheDocument()
  })

  it('opens a book and shows the pages the server laid out', async () => {
    stubApi({
      [SHELF]: { body: { items: [aBook()] } },
      [BOOK]: { body: { ...aBook(), leaves: LEAVES } },
    })

    await renderScreen(<PhotobooksScreen bookId="buch-1" />, { path: '/photobooks/buch-1' })

    expect(await screen.findByText('Zusammen im Auto')).toBeInTheDocument()
    // The line under the picture is the one the machine wrote, not the analyzer's sentence.
    expect(screen.getByText(/Lauri sitzt links im Auto/)).toBeInTheDocument()
  })

  it('says when a book cannot be opened', async () => {
    stubApi({
      [SHELF]: { body: { items: [aBook()] } },
      [BOOK]: { body: { ...aBook(), leaves: [] } },
    })

    await renderScreen(<PhotobooksScreen bookId="buch-1" />, { path: '/photobooks/buch-1' })

    expect(await screen.findByText(/lässt sich nicht aufschlagen/)).toBeInTheDocument()
  })

  it('turns the page with the arrow keys, two at a time on a desktop', async () => {
    render(<BookReader pages={LEAVES} title="Estland" onLeave={() => undefined} />)

    // Two pages lie open beside each other, and the bar says which.
    expect(screen.getByRole('navigation', { name: 'Estland' }).textContent).toContain('1–2 / 3')
    expect(screen.getByText('Zusammen im Auto')).toBeInTheDocument()

    await userEvent.keyboard('{ArrowRight}')

    await waitFor(() => {
      expect(screen.getByText('Der Grill ist an')).toBeInTheDocument()
    })
    expect(screen.queryByText('Zusammen im Auto')).not.toBeInTheDocument()

    await userEvent.keyboard('{ArrowLeft}')

    await waitFor(() => {
      expect(screen.getByText('Zusammen im Auto')).toBeInTheDocument()
    })
  })

  it('closes with Escape', async () => {
    const left = vi.fn()
    render(<BookReader pages={LEAVES} title="Estland" onLeave={left} />)

    await userEvent.keyboard('{Escape}')

    expect(left).toHaveBeenCalledOnce()
  })

  it('closes with a swipe down, and a page turn that wobbles does not close it', () => {
    // On a phone the cross sat under the status bar, out of reach of a finger.
    const left = vi.fn()
    const { container } = render(<BookReader pages={LEAVES} title="Estland" onLeave={left} />)
    const book = container.querySelector('.book') as HTMLElement
    const swipe = (dx: number, dy: number) => {
      fireEvent.touchStart(book, { touches: [{ clientX: 200, clientY: 200 }] })
      fireEvent.touchEnd(book, { changedTouches: [{ clientX: 200 + dx, clientY: 200 + dy }] })
    }

    swipe(-120, 40)
    swipe(0, -150)
    expect(left).not.toHaveBeenCalled()

    swipe(20, 150)
    expect(left).toHaveBeenCalledOnce()
  })

  it('shows one page at a time on a phone, and every page is a page that shows', () => {
    // The bug this guards: the side came from the absolute page number, and the stylesheet hid
    // every "right" page on a phone - so every second page was rendered and then blacked out.
    expect(sideOf(1, 0)).toBe('single')
    expect(sideOf(2, 0)).toBe('left')
    expect(sideOf(2, 1)).toBe('right')
  })
})
