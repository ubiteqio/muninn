import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { onLiveEvent } from '@/api/live'
import { getAccessToken } from '@/api/session'

/** Many changes in a row - an import, a thousand previews - become one reload. */
const BUNDLE_MS = 2000

/** The query keys that show what lies in the library. */
const LIBRARY_QUERIES = [['albums'], ['timeline'], ['media']] as const

/**
 * Keeps albums and timeline in step with the NAS while they are on screen.
 *
 * A file that appears is taken only after a second look, and its previews come later still -
 * long after the sync that first saw it has answered. The server says on the live channel when
 * the library changed; this reads what is shown again, at most once every two seconds.
 */
export function useLibraryUpdates(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    // Not signed in yet: the channel would only be refused.
    if (!getAccessToken()) return

    let timer: ReturnType<typeof setTimeout> | undefined
    const stop = onLiveEvent((event) => {
      if (event.topic !== 'library' || timer !== undefined) return
      timer = setTimeout(() => {
        timer = undefined
        for (const queryKey of LIBRARY_QUERIES) void queryClient.invalidateQueries({ queryKey })
      }, BUNDLE_MS)
    })

    return () => {
      stop()
      clearTimeout(timer)
    }
  }, [queryClient])
}
