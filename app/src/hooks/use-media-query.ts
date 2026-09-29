import { useCallback, useSyncExternalStore } from 'react'

/**
 * Tracks a CSS media query from JavaScript. Used where a breakpoint changes behaviour rather than
 * only appearance - the timeline renders three columns on mobile and eight on the desktop, and
 * rendering both would mean two grids fighting over the same element ids.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => {
        list.removeEventListener('change', onChange)
      }
    },
    [query],
  )

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query])

  // The app only renders in a browser; on the server the query is simply false.
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}

/** From 768 px the bottom navigation bar gives way to the sidebar. */
export const WIDE_QUERY = '(min-width: 768px)'

/** From 1024 px the design shows the sidebar plus a second content column. */
export const DESKTOP_QUERY = '(min-width: 1024px)'

/**
 * A screen with little height: a phone held sideways, or a small window.
 *
 * Width says how much room there is beside things; this says how much there is above and
 * below them. The rail of destinations is tall by nature, and a phone in landscape is 390 px
 * from edge to edge before the browser has taken its share.
 */
export const SHORT_QUERY = '(max-height: 560px)'
