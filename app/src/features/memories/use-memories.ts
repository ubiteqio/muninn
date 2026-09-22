import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type Memory = components['schemas']['MemoryView']

/** Today's look back. Chosen once a day on the server, so it may be kept for an hour here. */
export function useMemories() {
  return useQuery({
    queryKey: ['media', 'memories'],
    staleTime: 60 * 60 * 1000,
    queryFn: async () => {
      const found = await unwrap(await api.GET('/api/v1/memories'))
      return found.items
    },
  })
}
