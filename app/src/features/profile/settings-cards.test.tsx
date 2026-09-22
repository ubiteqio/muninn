import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { AppearanceCard } from '@/features/profile/appearance-card'
import { NotificationsCard } from '@/features/profile/notifications-card'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const SETTINGS = {
  push: {
    reply: true,
    mention: true,
    comment_like: true,
    comment: true,
    activity: false,
    new_media: true,
  },
  quiet_enabled: true,
  quiet_start: '22:00:00',
  quiet_end: '07:00:00',
}

describe('NotificationsCard', () => {
  it('saves a switch the moment it is flipped', async () => {
    const { calls } = stubApi({
      'GET /api/v1/me/notification-settings': { body: SETTINGS },
      'PUT /api/v1/me/notification-settings': {
        body: { ...SETTINGS, push: { ...SETTINGS.push, new_media: false } },
      },
    })
    await renderScreen(<NotificationsCard />)

    const newMedia = await screen.findByRole('switch', { name: 'Neue Alben oder Medien' })
    expect(newMedia).toHaveAttribute('aria-checked', 'true')
    // Not an admin: no admin alerts to switch.
    expect(screen.queryByRole('switch', { name: /NAS nicht erreichbar/ })).toBeNull()

    await userEvent.click(newMedia)

    await waitFor(() => {
      expect(newMedia).toHaveAttribute('aria-checked', 'false')
    })
    expect(calls.find((call) => call.method === 'PUT')?.body).toMatchObject({
      push: { new_media: false, reply: true },
    })
    expect(screen.getByText(/In der App erscheint immer alles/)).toBeInTheDocument()
  })
})

describe('AppearanceCard', () => {
  afterEach(() => {
    document.documentElement.classList.add('dark')
    localStorage.clear()
  })

  it('turns the page light at once and remembers it on this device', async () => {
    document.documentElement.classList.add('dark')
    await renderScreen(<AppearanceCard />)

    await userEvent.click(screen.getByRole('radio', { name: /Hell/ }))

    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(localStorage.getItem('muninn.theme')).toBe('light')
    expect(screen.getByRole('radio', { name: /Hell/ })).toHaveAttribute('aria-checked', 'true')
  })
})
