import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/features/auth/auth-store'
import { HomeScreen } from '@/features/home/home-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

describe('start screen', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(() => {
    // An empty library: the sections that belong to later milestones have nothing to show, and
    // the ones that are real have nothing yet either.
    stubApi({
      'GET /api/v1/albums/tree': { body: { items: [] } },
      'GET /api/v1/media/marks': { body: { by: 'month', total: 0, marks: [] } },
      'GET /api/v1/media': { body: { items: [], next_cursor: null, prev_cursor: null } },
      'GET /api/v1/media/periods': { body: [] },
      'GET /api/v1/memories': { body: { day: '2026-09-21', items: [] } },
    })
    useAuthStore.setState({
      status: 'signed-in',
      needsPasswordChange: false,
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        username: 'boris',
        email: 'boris@muninn.local',
        display_name: 'Boris Azar',
        role: 'admin',
        status: 'active',
        must_change_password: false,
        created_at: '2026-09-01T10:00:00Z',
        last_login_at: '2026-09-19T22:00:00Z',
      },
    })
  })

  it('shows all four sections', async () => {
    await renderScreen(<HomeScreen />)

    expect(screen.getByRole('heading', { name: 'Rückblicke' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Neuigkeiten' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Zuletzt hinzugefügt' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Zeitleiste' })).toBeInTheDocument()
  })

  it('asks for the latest five happenings only', async () => {
    const { calls } = stubApi({
      'GET /api/v1/albums/tree': { body: { items: [] } },
      'GET /api/v1/media/marks': { body: { by: 'month', total: 0, marks: [] } },
      'GET /api/v1/media': { body: { items: [], next_cursor: null, prev_cursor: null } },
      'GET /api/v1/media/periods': { body: [] },
      'GET /api/v1/activity': { body: { items: [], next_cursor: null } },
    })
    await renderScreen(<HomeScreen />)

    await waitFor(() => {
      const asked = calls.filter((call) => call.path === '/api/v1/activity')
      expect(asked.length).toBeGreaterThan(0)
      for (const call of asked) expect(new URL(call.url).searchParams.get('limit')).toBe('5')
    })
  })

  it('says what is not there yet instead of inventing it', async () => {
    await renderScreen(<HomeScreen />)

    expect(await screen.findByText(/Heute gibt es noch keine Rückblicke/)).toBeInTheDocument()
    expect(
      (
        await screen.findAllByText(
          'Noch ist es still. Kommentare, Likes und neue Bilder erscheinen hier.',
        )
      )[0],
    ).toBeInTheDocument()
    expect(screen.getAllByText(/Noch keine Alben/)[0]).toBeInTheDocument()
  })

  it('offers the bell, quiet while nothing is unread', async () => {
    await renderScreen(<HomeScreen />)

    expect(screen.getAllByRole('button', { name: 'Benachrichtigungen' }).length).toBeGreaterThan(0)
  })

  it('marks the start destination as the current page', async () => {
    await renderScreen(<HomeScreen />)

    const current = screen.getAllByRole('link', { current: 'page' })
    expect(current.length).toBeGreaterThan(0)
    for (const link of current) expect(link).toHaveAccessibleName('Home')
  })

  it('offers every navigation destination', async () => {
    await renderScreen(<HomeScreen />)

    for (const label of ['Home', 'Alben', 'Suche', 'Karte', 'Personen']) {
      expect(screen.getAllByRole('link', { name: label }).length).toBeGreaterThan(0)
    }
    // On the phone Überblick and Profil wait behind "Mehr".
    expect(screen.getByRole('button', { name: 'Mehr' })).toBeInTheDocument()
  })
})
