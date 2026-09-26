import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminSettingsPage } from '@/features/admin/settings-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const READ = 'GET /api/v1/admin/settings'
const WRITE = 'PUT /api/v1/admin/settings'

const settings = {
  thumbnail_size: 400,
  preview_size: 2048,
  image_quality: 82,
  video_height: 720,
  ignored_names: ['@eaDir', '#recycle'],
  quick_sync_seconds: 300,
  full_sync_hour: 3,
  stability_seconds: 30,
  missing_grace_days: 30,
  deletion_share_percent: 5,
  deletion_count: 500,
  nas_agent_enabled: false,
  updated_at: '2026-09-20T08:00:00Z',
}

/** Everything the PUT carries when nothing but the named field was touched. */
function bodyWith(changes: Record<string, unknown>) {
  // updated_at is the server's answer, never part of the request.
  const sent = Object.fromEntries(Object.entries(settings).filter(([key]) => key !== 'updated_at'))
  return { ...sent, ...changes }
}

function signedInAs(role: 'user' | 'admin') {
  useAuthStore.setState({
    status: 'signed-in',
    user: { ...aUser, role },
    needsPasswordChange: false,
  })
}

beforeEach(() => {
  signedInAs('admin')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Smarts in the settings', () => {
  it('stands among the things an admin sets, not in the engine room', async () => {
    stubApi({ [READ]: { body: settings } })

    await renderScreen(<AdminSettingsPage />)

    expect(await screen.findByRole('heading', { name: 'Smart-Alben' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neu erstellen' })).toBeInTheDocument()
  })
})

describe('settings', () => {
  it('shows the stored values', async () => {
    stubApi({ [READ]: { body: settings } })

    await renderScreen(<AdminSettingsPage />)

    expect(await screen.findByLabelText(/Vorschaubild im Raster/)).toHaveValue(400)
    expect(screen.getByLabelText(/Große Vorschau/)).toHaveValue(2048)
    expect(screen.getByText('@eaDir')).toBeInTheDocument()
  })

  it('sends every setting at once, because the endpoint replaces them', async () => {
    const { calls } = stubApi({
      [READ]: { body: settings },
      [WRITE]: { body: { ...settings, thumbnail_size: 320 } },
    })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const thumbnail = await screen.findByLabelText(/Vorschaubild im Raster/)
    await user.clear(thumbnail)
    await user.type(thumbnail, '320')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Gespeichert')
    expect(calls.find((call) => call.method === 'PUT')?.body).toEqual(
      bodyWith({ thumbnail_size: 320 }),
    )
  })

  it('refuses a preview that is not larger than the thumbnail, without asking the server', async () => {
    stubApi({ [READ]: { body: settings } })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const thumbnail = await screen.findByLabelText(/Vorschaubild im Raster/)
    await user.clear(thumbnail)
    await user.type(thumbnail, '900')
    const preview = screen.getByLabelText(/Große Vorschau/)
    await user.clear(preview)
    await user.type(preview, '850')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('größer sein')
  })

  it('refuses a size outside the bounds', async () => {
    stubApi({ [READ]: { body: settings } })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const thumbnail = await screen.findByLabelText(/Vorschaubild im Raster/)
    await user.clear(thumbnail)
    await user.type(thumbnail, '20')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('zwischen 100 und 1000')
  })

  it('adds and removes an ignored name', async () => {
    const { calls } = stubApi({
      [READ]: { body: settings },
      [WRITE]: { body: settings },
    })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Name hinzufügen'), 'Thumbs.db')
    await user.click(screen.getByRole('button', { name: 'Hinzufügen' }))
    await user.click(screen.getByRole('button', { name: '#recycle entfernen' }))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(calls.find((call) => call.method === 'PUT')?.body).toMatchObject({
      ignored_names: ['@eaDir', 'Thumbs.db'],
    })
  })

  it('takes a path for an ignored name as a mistake', async () => {
    stubApi({ [READ]: { body: settings } })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Name hinzufügen'), 'fotos/2009')
    await user.click(screen.getByRole('button', { name: 'Hinzufügen' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('kein Pfad')
  })

  it('keeps a plain user out of the area', async () => {
    signedInAs('user')
    stubApi({})

    await renderScreen(<AdminSettingsPage />)

    expect(screen.queryByRole('navigation', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('switches between the two sections', async () => {
    stubApi({ [READ]: { body: settings } })

    await renderScreen(<AdminSettingsPage />)

    const sections = within(await screen.findByRole('navigation', { name: 'Admin' }))
    expect(sections.getByRole('link', { name: 'Einstellungen' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(sections.getByRole('link', { name: 'Benutzer' })).toHaveAttribute('href', '/admin/users')
  })
})

describe('the settings of the sync', () => {
  it('shows the values the concept lists', async () => {
    stubApi({ [READ]: { body: settings } })

    await renderScreen(<AdminSettingsPage />)

    expect(await screen.findByLabelText(/Schnell-Abgleich/)).toHaveValue(300)
    expect(screen.getByLabelText(/Schonfrist/)).toHaveValue(30)
    expect(screen.getByLabelText(/Löschpause: Anteil/)).toHaveValue(5)
  })

  it('lets the grace period be set to nothing', async () => {
    const { calls } = stubApi({
      [READ]: { body: settings },
      [WRITE]: { body: { ...settings, missing_grace_days: 0 } },
    })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const grace = await screen.findByLabelText(/Schonfrist/)
    await user.clear(grace)
    await user.type(grace, '0')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(calls.find((call) => call.method === 'PUT')?.body).toEqual(
      bodyWith({ missing_grace_days: 0 }),
    )
  })

  it('lets the pause before deletions be switched off', async () => {
    const { calls } = stubApi({
      [READ]: { body: settings },
      [WRITE]: { body: { ...settings, deletion_share_percent: 0 } },
    })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const share = await screen.findByLabelText(/Löschpause: Anteil/)
    await user.clear(share)
    await user.type(share, '0')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'PUT')?.body).toMatchObject({
        deletion_share_percent: 0,
      })
    })
  })

  it('keeps the pause within its bounds', async () => {
    stubApi({ [READ]: { body: settings } })
    await renderScreen(<AdminSettingsPage />)
    const user = userEvent.setup()

    const share = await screen.findByLabelText(/Löschpause: Anteil/)
    await user.clear(share)
    await user.type(share, '80')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('zwischen 0 und 50')
  })
})
