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
    if (!node) return undefined

    const measure = () => {
      setWidth(node.getBoundingClientRect().width)
    }

    /*
     * Turning a phone is not an ordinary resize. iOS reports the old screen while the rotation
     * is still running, and the observer fires with it - so the grid kept the columns of the
     * orientation it was in until something else made it measure again. It is measured once
     * more when the turn has settled: after two frames, and a beat later for the browser whose
     * bars are still sliding into place.
     */
    let again = 0
    const turned = () => {
      window.clearTimeout(again)
      requestAnimationFrame(() => {
        requestAnimationFrame(measure)
      })
      again = window.setTimeout(measure, 300)
    }

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(([entry]) => {
            setWidth(entry?.contentRect.width ?? 0)
          })
    observer?.observe(node)
    window.addEventListener('orientationchange', turned)
    window.visualViewport?.addEventListener('resize', turned)

    return () => {
      window.clearTimeout(again)
      observer?.disconnect()
      window.removeEventListener('orientationchange', turned)
      window.visualViewport?.removeEventListener('resize', turned)
    }
  }, [element])

  return width
}
