import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type Analysis = components['schemas']['AnalysisView']
export type Transcript = components['schemas']['TranscriptView']

/**
 * One medium as the detail view has it - with what the AI saw, which the lists leave out.
 * Asked for only while the info panel is open; a description changes rarely.
 */
export function useMediumDetail(mediaId: string) {
  return useQuery({
    queryKey: ['media', mediaId],
    staleTime: 60_000,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/media/{media_id}', { params: { path: { media_id: mediaId } } }),
      ),
  })
}
