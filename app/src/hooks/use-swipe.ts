import { useEffect, useRef } from 'react'

/** How far a finger travels before it means a swipe, and how much straighter than the other axis. */
const DISTANCE = 70
const STRAIGHTNESS = 1.6
/** Slower than this and it was a drag or a scroll that came to rest, not a swipe. */
const LONGEST_MS = 800
/** A drag from the very edge is the browser's own "back"; a swipe keeps out of its way. */
const EDGE = 24

export interface Swipes {
  onLeft?: () => void
  onRight?: () => void
  onUp?: () => void
  onDown?: () => void
}

/**
 * Whether the finger came down on something that scrolls sideways by itself - the breadcrumb, a
 * row of pills. That gesture belongs to the row, not to the screen behind it.
 */
function onASidewaysScroller(target: EventTarget | null): boolean {
  let node = target instanceof Element ? target : null
  while (node) {
    if (node.scrollWidth > node.clientWidth + 1) {
      const how = getComputedStyle(node).overflowX
      if (how === 'auto' || how === 'scroll') return true
    }
    node = node.parentElement
  }
  return false
}

/**
 * A swipe of one finger across the screen, for a phone.
 *
 * Only touches, so nothing changes on a desktop. One finger only - two are a zoom or a scroll of
 * something else - and the gesture has to be long and straight to count, so an ordinary scroll
 * that drifts a little sideways is not mistaken for one.
 */
export function useSwipe(swipes: Swipes, enabled = true): void {
  const latest = useRef(swipes)
  useEffect(() => {
    latest.current = swipes
  })

  useEffect(() => {
    if (!enabled) return undefined
    let from: { x: number; y: number; at: number } | null = null

    const began = (event: TouchEvent) => {
      const touch = event.touches[0]
      from = null
      if (event.touches.length !== 1 || !touch) return
      if (touch.clientX < EDGE || touch.clientX > window.innerWidth - EDGE) return
      if (onASidewaysScroller(event.target)) return
      from = { x: touch.clientX, y: touch.clientY, at: Date.now() }
    }

    const ended = (event: TouchEvent) => {
      const start = from
      from = null
      const touch = event.changedTouches[0]
      if (!start || !touch || Date.now() - start.at > LONGEST_MS) return
      const across = touch.clientX - start.x
      const down = touch.clientY - start.y
      if (Math.abs(across) >= DISTANCE && Math.abs(across) > Math.abs(down) * STRAIGHTNESS) {
        if (across < 0) latest.current.onLeft?.()
        else latest.current.onRight?.()
      } else if (Math.abs(down) >= DISTANCE && Math.abs(down) > Math.abs(across) * STRAIGHTNESS) {
        if (down < 0) latest.current.onUp?.()
        else latest.current.onDown?.()
      }
    }

    window.addEventListener('touchstart', began, { passive: true })
    window.addEventListener('touchend', ended, { passive: true })
    return () => {
      window.removeEventListener('touchstart', began)
      window.removeEventListener('touchend', ended)
    }
  }, [enabled])
}
