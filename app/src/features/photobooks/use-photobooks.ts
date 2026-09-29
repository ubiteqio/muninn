import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { onLiveEvent } from '@/api/live'
import { getAccessToken } from '@/api/session'

export type Photobook = components['schemas']['PhotobookView']
export type PhotobookRead = components['schemas']['PhotobookRead']
export type NewPhotobook = components['schemas']['NewPhotobook']

/** One page of a book, as the server stored it. The shapes differ per kind, so this is loose. */
export type Leaf = Record<string, unknown>

const SHELF_KEY = ['photobooks'] as const

/**
 * The shelf: every book, newest first.
 *
 * A book is built once and kept, so this is a plain query with no paging - a family has books,
 * not thousands of them - and it costs nothing to open while the AI machine is off.
 */
export function usePhotobooks() {
  return useQuery({
    queryKey: SHELF_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/photobooks')),
  })
}

/** One book with all its pages, each picture addressed and signed for this hour. */
export function usePhotobook(bookId: string | undefined) {
  return useQuery({
    queryKey: ['photobooks', bookId ?? ''],
    enabled: bookId !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/photobooks/{book_id}', {
          params: { path: { book_id: bookId ?? '' } },
        }),
      ),
  })
}

/**
 * Keeps the shelf in step with the worker.
 *
 * Books are ordered in the admin area and filled minutes later by a worker, often while
 * somebody else has the shelf open. The server says on the live channel when that happened; the
 * shelf then reads itself again rather than showing "wird gebaut" until the next reload.
 */
export function usePhotobookUpdates(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!getAccessToken()) return

    return onLiveEvent((event) => {
      if (event.topic !== 'photobooks') return
      void queryClient.invalidateQueries({ queryKey: SHELF_KEY })
    })
  }, [queryClient])
}

/** Ordering books of an album. The answer comes at once; the pages follow from the worker. */
export function useMakePhotobooks() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (wanted: NewPhotobook) =>
      unwrap(await api.POST('/api/v1/photobooks', { body: wanted })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHELF_KEY }),
  })
}

/** Removing a book. Not one picture is touched by it. */
export function useRemovePhotobook() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (bookId: string) =>
      unwrap(
        await api.DELETE('/api/v1/photobooks/{book_id}', {
          params: { path: { book_id: bookId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHELF_KEY }),
  })
}

/** Building a book anew - after the album grew, or after the machine was away. */
export function useRebuildPhotobook() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (bookId: string) =>
      unwrap(
        await api.POST('/api/v1/photobooks/{book_id}/rebuild', {
          params: { path: { book_id: bookId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHELF_KEY }),
  })
}

/** The albums an admin may make a book of: the published folders that hold media. */
export function usePublishedAlbums() {
  return useQuery({
    queryKey: ['albums', 'tree'],
    queryFn: async () => unwrap(await api.GET('/api/v1/albums/tree')),
    select: (tree) =>
      tree.items
        .filter((album) => album.media_count > 0)
        .sort((one, other) => one.relative_path.localeCompare(other.relative_path)),
  })
}
