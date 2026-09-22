import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import type { Medium } from '@/features/albums/use-albums'
import { loadStyle } from '@/features/map/map-style'

export type Cluster = components['schemas']['ClusterView']
export type Bounds = components['schemas']['BoundsView']
type MediaPage = components['schemas']['Page_MediaView_']

/** The visible part of the map and the zoom level its clusters are made for. */
export interface View extends Bounds {
  zoom: number
}

/** The points of the visible part, grouped. The last answer stays while the next one comes. */
export function useClusters(view: View | null) {
  return useQuery({
    queryKey: ['media', 'map', 'clusters', view],
    enabled: view !== null,
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<Cluster[]> => {
      if (view === null) return []
      const found = await unwrap(await api.GET('/api/v1/map/clusters', { params: { query: view } }))
      return found.items
    },
  })
}

const PAGE_SIZE = 60

/** What a tapped cluster holds, newest first. */
export function useAreaMedia(area: Bounds | null) {
  const query = useInfiniteQuery({
    queryKey: ['media', 'map', 'area', area],
    enabled: area !== null,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: MediaPage) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }): Promise<MediaPage> => {
      if (area === null) return { items: [] }
      return unwrap(
        await api.GET('/api/v1/map/media', {
          params: {
            query: { ...area, limit: PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) },
          },
        }),
      )
    },
  })
  const media: Medium[] = query.data?.pages.flatMap((page) => page.items) ?? []
  return { ...query, media }
}

/** The basemap for light or dark. Fetched once per look; a failure leaves the plain one. */
export function useMapStyle(dark: boolean) {
  return useQuery({
    queryKey: ['map', 'style', dark],
    staleTime: Infinity,
    retry: 1,
    queryFn: () => loadStyle(dark),
  })
}
