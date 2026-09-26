import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { onLiveEvent } from '@/api/live'
import { getAccessToken } from '@/api/session'

/**
 * Keeps the Smarts in step with a run that happened somewhere else.
 *
 * A run replaces every chapter, and it is started in the admin area - often in another window,
 * sometimes on another machine. What is on this screen then no longer exists: opening one of
 * its cards would ask for a chapter that has been deleted. The server says on the live channel
 * that they were found anew; everything in hand is thrown away rather than marked stale,
 * because it is not an older version of the same thing.
 */
export function useSmartsUpdates(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!getAccessToken()) return

    return onLiveEvent((event) => {
      if (event.topic !== 'smarts') return
      void queryClient.resetQueries({ queryKey: ['smarts'] })
    })
  }, [queryClient])
}
