import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { type Swipes, useSwipe } from '@/hooks/use-swipe'

function touched(type: 'touchstart' | 'touchend', x: number, y: number) {
  const event = new Event(type, { bubbles: true })
  const points = [{ clientX: x, clientY: y }]
  Object.defineProperty(event, 'touches', { value: type === 'touchend' ? [] : points })
  Object.defineProperty(event, 'changedTouches', { value: points })
  return event
}

function swipe(from: [number, number], to: [number, number]) {
  window.dispatchEvent(touched('touchstart', from[0], from[1]))
  window.dispatchEvent(touched('touchend', to[0], to[1]))
}

function listening(enabled = true) {
  const swipes: Required<Swipes> = {
    onLeft: vi.fn(),
    onRight: vi.fn(),
    onUp: vi.fn(),
    onDown: vi.fn(),
  }
  renderHook(() => {
    useSwipe(swipes, enabled)
  })
  return swipes
}

describe('useSwipe', () => {
  it('reads a long straight drag as a swipe', () => {
    const swipes = listening()

    swipe([300, 400], [180, 410])
    expect(swipes.onLeft).toHaveBeenCalledOnce()

    swipe([300, 400], [420, 390])
    expect(swipes.onRight).toHaveBeenCalledOnce()

    swipe([300, 400], [305, 280])
    expect(swipes.onUp).toHaveBeenCalledOnce()
  })

  it('leaves an ordinary scroll alone', () => {
    const swipes = listening()

    // Reading on: far up the screen, and a little sideways on the way. Not a swipe sideways.
    swipe([300, 500], [340, 300])

    expect(swipes.onLeft).not.toHaveBeenCalled()
    expect(swipes.onRight).not.toHaveBeenCalled()
    expect(swipes.onUp).toHaveBeenCalledOnce()
  })

  it('ignores a drag too short to have been meant', () => {
    const swipes = listening()

    swipe([300, 400], [250, 400])

    expect(swipes.onLeft).not.toHaveBeenCalled()
  })

  it('keeps out of the way of the browser at the edge', () => {
    const swipes = listening()

    // iOS reads a drag from the very edge as its own "back".
    swipe([8, 400], [300, 400])

    expect(swipes.onRight).not.toHaveBeenCalled()
  })

  it('does nothing while it is switched off', () => {
    const swipes = listening(false)

    swipe([300, 400], [180, 400])

    expect(swipes.onLeft).not.toHaveBeenCalled()
  })
})
