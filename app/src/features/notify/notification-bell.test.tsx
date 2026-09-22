import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { NotificationBell } from '@/features/notify/notification-bell'
import { people } from '@/features/notify/use-notifications'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aNotice(extra: object) {
  return {
    id: 'n1',
    kind: 'reply',
    actors: ['Boris'],
    count: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    read: false,
    media: { id: 'media-1', kind: 'image', album_id: 'album-1', thumb: null },
    album: { id: 'album-1', title: 'Venedig' },
    excerpt: 'In Venedig!',
    ...extra,
  }
}

describe('NotificationBell', () => {
  it('counts what is new, lists it, and reads it all when opened', async () => {
    const { calls } = stubApi({
      'GET /api/v1/notifications/unread': { body: { count: 2 } },
      'GET /api/v1/notifications': {
        body: {
          next_cursor: null,
          items: [
            aNotice({}),
            aNotice({
              id: 'n2',
              kind: 'new_media',
              actors: [],
              count: 12,
              media: null,
              album: { id: 'album-2', title: 'Radtour' },
              excerpt: null,
            }),
          ],
        },
      },
      'POST /api/v1/notifications/read': { status: 204 },
    })
    await renderScreen(<NotificationBell />)

    const bell = await screen.findByRole('button', { name: /Benachrichtigungen/ })
    await waitFor(() => {
      expect(bell).toHaveTextContent('2')
    })
    await userEvent.click(bell)

    expect(
      await screen.findByText('Boris hat auf deinen Kommentar geantwortet'),
    ).toBeInTheDocument()
    expect(screen.getByText('12 neue Medien in Radtour')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Boris hat/ })).toHaveAttribute(
      'href',
      '/albums/album-1?medium=media-1',
    )
    await waitFor(() => {
      expect(calls.some((call) => call.path === '/api/v1/notifications/read')).toBe(true)
    })
  })
})

describe('the people in words', () => {
  const t = ((key: string, values: Record<string, unknown>) =>
    key === 'notify.two'
      ? `${String(values.first)} und ${String(values.second)}`
      : `${String(values.first)} und ${String(values.count)} weitere`) as never

  it.each([
    [['Anna'], 1, 'Anna'],
    [['Anna', 'Boris'], 2, 'Anna und Boris'],
    [['Anna', 'Boris', 'Lena'], 3, 'Anna und 2 weitere'],
  ])('%j', (names, count, said) => {
    expect(people(names, count, t)).toBe(said)
  })
})
