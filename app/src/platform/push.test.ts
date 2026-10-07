import { beforeEach, describe, expect, it, vi } from 'vitest'

import { stubApi } from '@/test/api-stub'

type Listener = (event: never) => void

const plugin = vi.hoisted(() => ({
  platform: 'ios',
  permission: 'prompt',
  listeners: new Map<string, (event: unknown) => void>(),
  registered: 0,
}))

vi.mock('@capacitor/core', () => ({
  Capacitor: {
    getPlatform: () => plugin.platform,
    isNativePlatform: () => plugin.platform !== 'web',
  },
}))

vi.mock('@capacitor/push-notifications', () => ({
  PushNotifications: {
    addListener: (name: string, listener: Listener) => {
      plugin.listeners.set(name, listener as (event: unknown) => void)
      return Promise.resolve({ remove: () => Promise.resolve() })
    },
    checkPermissions: () => Promise.resolve({ receive: plugin.permission }),
    requestPermissions: () => {
      plugin.permission = 'granted'
      return Promise.resolve({ receive: 'granted' })
    },
    register: () => {
      plugin.registered += 1
      return Promise.resolve()
    },
  },
}))

const { startPush, stopPush } = await import('@/platform/push')

beforeEach(() => {
  plugin.platform = 'ios'
  plugin.permission = 'prompt'
  plugin.registered = 0
  localStorage.clear()
})

describe('push on the iPhone', () => {
  it('asks once, tells the server the phone, and opens a tapped push', async () => {
    const { calls } = stubApi({ 'POST /api/v1/me/devices': { status: 204 } })
    const opened = vi.fn()

    await startPush(opened)
    expect(plugin.registered).toBe(1)

    // Apple hands out the token: the server learns which phone this is.
    plugin.listeners.get('registration')?.({ value: 'apns-token-1' })
    await vi.waitFor(() => {
      expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
        platform: 'ios',
        token: 'apns-token-1',
      })
    })

    plugin.listeners.get('pushNotificationActionPerformed')?.({
      notification: { data: { media_id: 'm1', album_id: 'a1', notification_id: 'n1' } },
    })
    expect(opened).toHaveBeenCalledWith({ mediaId: 'm1', albumId: 'a1' })
  })

  it('forgets the phone on sign-out', async () => {
    const { calls } = stubApi({
      'POST /api/v1/me/devices': { status: 204 },
      'DELETE /api/v1/me/devices/apns-token-1': { status: 204 },
    })
    await startPush(vi.fn())
    plugin.listeners.get('registration')?.({ value: 'apns-token-1' })

    await stopPush()

    expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
  })

  it('leaves a phone alone that said no', async () => {
    plugin.permission = 'denied'

    await startPush(vi.fn())

    expect(plugin.registered).toBe(0)
  })

  it('does nothing in the browser', async () => {
    plugin.platform = 'web'

    await startPush(vi.fn())
    await stopPush()

    expect(plugin.registered).toBe(0)
  })
})
