import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { rememberTokens } from '@/api/session'
import { useSmartsUpdates } from '@/features/smarts/use-smarts-updates'

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

describe('useSmartsUpdates', () => {
  beforeEach(async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    await rememberTokens({ accessToken: 'access-token-1' })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws away the chapters when they were found anew somewhere else', async () => {
    const client = new QueryClient()
    client.setQueryData(['smarts'], { chapters: ['von vorher'] })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    renderHook(
      () => {
        useSmartsUpdates()
      },
      { wrapper },
    )
    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      FakeSocket.last?.say({ topic: 'smarts', kind: 'rebuilt', chapters: 21, at: '' })
    })

    // Not stale, gone: a run deletes every chapter and writes new ones with new ids.
    expect(client.getQueryData(['smarts'])).toBeUndefined()
  })

  it('leaves them alone while something else happens in the house', async () => {
    const client = new QueryClient()
    client.setQueryData(['smarts'], { chapters: ['von vorher'] })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    renderHook(
      () => {
        useSmartsUpdates()
      },
      { wrapper },
    )
    await act(async () => {
      await Promise.resolve()
    })

    act(() => {
      FakeSocket.last?.say({ topic: 'library', kind: 'changed', at: '' })
      FakeSocket.last?.say({ topic: 'jobs', kind: 'task_finished', at: '' })
    })

    expect(client.getQueryData(['smarts'])).toEqual({ chapters: ['von vorher'] })
  })
})
