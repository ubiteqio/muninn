import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useTicker } from '@/hooks/use-ticker'

afterEach(() => {
  vi.useRealTimers()
})

describe('the ticker', () => {
  it('moves on while something on screen is told in relative time', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useTicker(true))
    const first = result.current

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current).toBeGreaterThanOrEqual(first + 3000)
  })

  it('stands still when nothing depends on the passing time', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useTicker(false))
    const first = result.current

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(result.current).toBe(first)
  })
})
