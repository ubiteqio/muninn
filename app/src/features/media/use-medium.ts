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

/**
 * One medium, asked for only when something points at a picture that is not on the page.
 *
 * An album is read a page at a time, and the viewer is built from the page that is loaded. A
 * link from elsewhere - the engine room naming the file it has just finished - may point deep
 * into an album of thousands, where that medium is on no page anybody has asked for yet, and
 * the viewer had nothing to open: the click did nothing at all.
 *
 * This fetches that one picture so it can be shown on its own. There is no way to ask the
 * server for "the page this medium is on", and a picture without its neighbours is better
 * than a link that does nothing.
 */
export function useMediumAlone(mediaId: string | undefined) {
  return useQuery({
    queryKey: ['media', mediaId],
    enabled: mediaId !== undefined,
    staleTime: 60_000,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/media/{media_id}', {
          params: { path: { media_id: mediaId ?? '' } },
        }),
      ),
  })
}
