import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { rememberTokens } from '@/api/session'
import { useLibraryUpdates } from '@/features/albums/use-library-updates'

/** A WebSocket the test can push messages into. */
class FakeSocket extends EventTarget {
  static last: FakeSocket | null = null
  constructor() {
    super()
    FakeSocket.last = this
  }
  close() {}
  say(event: object) {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }))
  }
}

describe('useLibraryUpdates', () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeSocket)
    await rememberTokens({ accessToken: 'access-token-1' })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('reads albums and timeline again once, however many changes come in', async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    renderHook(
      () => {
        useLibraryUpdates()
      },
      { wrapper },
    )
    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      for (let index = 0; index < 50; index++) {
        FakeSocket.last?.say({ topic: 'library', kind: 'changed', at: '' })
      }
      FakeSocket.last?.say({ topic: 'jobs', kind: 'task_finished', at: '' })
    })
    expect(invalidate).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      ['albums'],
      ['timeline'],
      ['media'],
    ])
  })
})
