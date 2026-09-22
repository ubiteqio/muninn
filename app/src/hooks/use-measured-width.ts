import { type RefObject, useEffect, useState } from 'react'

/**
 * The width of an element, kept up to date.
 *
 * Grids that place their own tiles need a number, not a percentage. Zero until the first
 * measurement, and zero wherever there is no layout at all, so callers fall back to a plain
 * grid rather than waiting for a measurement that may never come.
 */
export function useMeasuredWidth(element: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const node = element.current
    if (!node || typeof ResizeObserver === 'undefined') return

    const observer = new ResizeObserver(([entry]) => {
      setWidth(entry?.contentRect.width ?? 0)
    })
    observer.observe(node)
    return () => {
      observer.disconnect()
    }
  }, [element])

  return width
}
