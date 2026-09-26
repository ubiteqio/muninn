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
 * Build chapters now, until this many have come out of it.
 *
 * It runs while the request is open - an album of a few thousand takes seconds - so the answer
 * says what was built rather than that something was queued somewhere.
 */
export function useRebuildSmarts() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (chapters: number) =>
      unwrap(await api.POST('/api/v1/smarts/build', { body: { chapters } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: STATE_KEY })
      // The Smarts screen shows what was just built the next time somebody opens it.
      void queryClient.invalidateQueries({ queryKey: ['smarts'] })
    },
  })
}
