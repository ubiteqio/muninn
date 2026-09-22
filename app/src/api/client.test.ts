import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, apiServerChanged } from '@/api/client'
import { forgetServer, rememberServer } from '@/platform/server'

// The native app: loaded from inside the phone, talking to a server somewhere in the house.
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => true, getPlatform: () => 'ios' },
}))

function answer(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      Promise.resolve(
        new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
      ),
    ),
  )
}

describe('the API client in the native app', () => {
  beforeEach(() => {
    rememberServer('192.168.178.4:9090')
    apiServerChanged()
  })

  afterEach(() => {
    forgetServer()
    vi.unstubAllGlobals()
  })

  it('puts the server in front of every picture address, however deep it sits', async () => {
    answer({
      items: [
        {
          id: 'm1',
          relative_path: 'Urlaub/strand.jpg',
          urls: { thumb: '/api/v1/media/m1/thumb?token=1.a', video: null },
        },
      ],
      cover: '/api/v1/media/m2/thumb?token=2.b',
    })

    const { data } = await api.GET('/api/v1/media')

    expect(data).toEqual({
      items: [
        {
          id: 'm1',
          relative_path: 'Urlaub/strand.jpg',
          urls: { thumb: 'http://192.168.178.4:9090/api/v1/media/m1/thumb?token=1.a', video: null },
        },
      ],
      cover: 'http://192.168.178.4:9090/api/v1/media/m2/thumb?token=2.b',
    })
  })
})
