import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type SmartsState = components['schemas']['SmartsState']
export type BuildResult = components['schemas']['BuildResult']

const STATE_KEY = ['admin', 'smarts'] as const

/** What the Smarts hold: how many chapters, over how many albums, and what is still outstanding. */
export function useSmartsState() {
  return useQuery({
    queryKey: STATE_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/smarts/state')),
  })
}

/**
 * Find the smart albums now, with the numbers as they are saved.
 *
 * It runs while the request is open - the whole library takes seconds - so the answer says what
 * was built rather than that something was queued somewhere.
 */
export function useRebuildSmarts() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/v1/smarts/build', { body: {} })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: STATE_KEY })
      // Thrown away rather than marked stale: a run writes new chapters with new ids, so what
      // is in hand is not an older version of the same thing - it is gone. A page kept from
      // before would ask for a chapter that no longer exists.
      void queryClient.resetQueries({ queryKey: ['smarts'] })
    },
  })
}
