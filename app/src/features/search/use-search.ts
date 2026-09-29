import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type SearchPage = components['schemas']['SearchPage']
export type SearchHit = components['schemas']['SearchHitView']
export type SearchAbilities = components['schemas']['SearchAbilities']
export type Facets = components['schemas']['FacetsView']
export type MediaKind = 'image' | 'video'
export type SearchSort = 'relevance' | 'date'

export interface SearchInput {
  q: string
  kind?: MediaKind | undefined
  sort?: SearchSort | undefined
  /** One year, as the overview counts them. */
  year?: number | undefined
  /** A town, as the overview names it. */
  place?: string | undefined
  camera?: string | undefined
  /** An album and everything below it. */
  album?: string | undefined
  /** Pictures like this medium instead of words. */
  similar?: string | undefined
}

const PAGE_SIZE = 60

/**
 * One search, page after page. Nothing is asked while there is nothing to ask: an empty field
 * shows a hint, not the whole library.
 */
export function useSearch({ q, kind, sort, year, place, camera, album, similar }: SearchInput) {
  const words = q.trim()
  const narrowed = [kind ?? null, sort ?? 'relevance', year ?? null, place ?? null, camera ?? null, album ?? null]

  return useInfiniteQuery({
    queryKey: ['media', 'search', similar ?? null, words, ...narrowed],
    enabled: words.length > 0 || similar !== undefined,
    // A different filter on the same words keeps the pictures on screen while the new page is
    // on its way: a grid that empties and fills again reads as a page that jumped. New words
    // are a new question, though, and then the old answer standing there is a lie - it goes,
    // and the field says that Muninn is looking.
    placeholderData: (previous, of) => (of?.queryKey[3] === words ? previous : undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: SearchPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<SearchPage> => {
      if (similar !== undefined) {
        return unwrap(
          await api.GET('/api/v1/media/{media_id}/similar', {
            params: {
              path: { media_id: similar },
              query: { limit: PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) },
            },
          }),
        )
      }
      return unwrap(
        await api.POST('/api/v1/search', {
          body: {
            q: words,
            sort: sort ?? 'relevance',
            limit: PAGE_SIZE,
            ...(kind ? { kind } : {}),
            // One year, as a period: the first day of it until the first day of the next.
            ...(year
              ? { date_from: `${String(year)}-01-01`, date_until: `${String(year + 1)}-01-01` }
              : {}),
            ...(place ? { place } : {}),
            ...(camera ? { camera } : {}),
            ...(album ? { album_id: album } : {}),
            ...(pageParam ? { cursor: pageParam } : {}),
          },
        }),
      )
    },
  })
}

/**
 * What the search can look into, by the AI models in use. Without a picture and a word model it
 * still finds names, places and periods - the search page says so, and "Ähnliche Bilder" is not
 * offered where there is nothing to compare. Changes only when an admin sets up a model.
 */
/** Asked again whenever an admin changes the AI profiles. */
export const ABILITIES_KEY = ['search', 'abilities'] as const

export function useSearchAbilities() {
  return useQuery({
    queryKey: ABILITIES_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/search/abilities')),
    // Which models are set up changes rarely; whether their machine answers changes by itself.
    // Asked again now and then, and whenever the window is looked at, so the field follows the
    // machine instead of waiting for a reload.
    staleTime: 20_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
}
