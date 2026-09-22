import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type Album = components['schemas']['AlbumView']
export type Medium = components['schemas']['MediaView']

const TREE_KEY = ['albums', 'tree'] as const

/**
 * Yggdrasil in one request.
 *
 * The whole tree is a few thousand rows at most, and having it in hand makes every path, every
 * list of subalbums and every breadcrumb a lookup rather than another round trip.
 */
export function useAlbumTree() {
  return useQuery({
    queryKey: TREE_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/albums/tree')),
    select: (tree) => {
      const byId = new Map(tree.items.map((album) => [album.id, album]))
      const children = new Map<string | null, Album[]>()
      for (const album of tree.items) {
        const siblings = children.get(album.parent_id) ?? []
        siblings.push(album)
        children.set(album.parent_id, siblings)
      }
      return { items: tree.items, byId, children }
    },
  })
}

/** Where in an album a page sits: forwards from one medium, or backwards from another. */
export interface MediaPagePosition {
  cursor?: string | undefined
  before?: string | undefined
}

/**
 * One page of an album, oldest first.
 *
 * Which page that is comes from the address, so the answer is a plain query rather than a
 * growing list: paging forwards and back lands on the same pages every time, and the page one
 * is looking at can be sent to somebody else. While the next page is on its way the current one
 * stays on screen - a grid that empties out and fills again reads as a page that jumped.
 */
export function useAlbumMedia(albumId: string | undefined, at: MediaPagePosition = {}) {
  return useQuery({
    queryKey: ['albums', albumId, 'media', at.cursor ?? null, at.before ?? null],
    enabled: albumId !== undefined,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/albums/{album_id}/media', {
          params: {
            path: { album_id: albumId ?? '' },
            query: {
              ...(at.cursor === undefined ? {} : { cursor: at.cursor }),
              ...(at.before === undefined ? {} : { before: at.before }),
            },
          },
        }),
      ),
  })
}

/** The albums from a root down to this one, for the path above the grid. */
export function pathTo(album: Album | undefined, byId: Map<string, Album>): Album[] {
  const path: Album[] = []
  let current = album
  while (current) {
    path.unshift(current)
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return path
}

/** How often the app asks how a requested sync is going, until the WebSocket takes over. */
const SYNC_POLL_MS = 2000

export type SyncJob = components['schemas']['AlbumSyncJob']

/**
 * "Sync now" in an album's header.
 *
 * Open to everybody signed in, because it only reads the NAS. The answer is a job id; until
 * milestone 5 brings the WebSocket, the app asks every couple of seconds how far it got.
 */
export function useAlbumSync(albumId: string | undefined) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: async (withChildren: boolean) =>
      unwrap(
        await api.POST('/api/v1/albums/{album_id}/sync', {
          params: { path: { album_id: albumId ?? '' } },
          body: { with_children: withChildren },
        }),
      ),
    onSuccess: (queued) => {
      setJobId(queued.job_id)
    },
  })

  const job = useQuery({
    queryKey: ['albums', albumId, 'sync', jobId],
    enabled: albumId !== undefined && jobId !== null,
    refetchInterval: (query) => (query.state.data?.state === 'done' ? false : SYNC_POLL_MS),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/albums/{album_id}/sync/{job_id}', {
          params: { path: { album_id: albumId ?? '', job_id: jobId ?? '' } },
        }),
      ),
  })

  const done = job.data?.state === 'done'

  useEffect(() => {
    // What the sync found is in the database now, so the album has to be read again.
    if (done) void queryClient.invalidateQueries({ queryKey: ['albums'] })
  }, [done, queryClient])

  return {
    start: (withChildren: boolean) => {
      start.mutate(withChildren)
    },
    isRunning: start.isPending || (jobId !== null && !done),
    result: done ? (job.data?.result ?? null) : null,
    error: start.error,
  }
}
