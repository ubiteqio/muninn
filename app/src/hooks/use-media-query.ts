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
