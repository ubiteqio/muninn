import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { JOBS_KEY } from '@/features/admin/use-jobs'

export type Publication = components['schemas']['PublicationView']
export type ScanStatus = components['schemas']['ScanStatus']
export type FolderEntry = components['schemas']['FolderEntry']
export type IndexStatus = components['schemas']['IndexStatus']

const STATUS_KEY = ['admin', 'index-status'] as const
const BROWSE_KEY = ['admin', 'library-browse'] as const
/** What the library itself is built from; a sync changes it, so it has to be read again. */
const ALBUMS_KEY = ['albums'] as const

/** While a sync runs the numbers keep moving, so the page asks again every few seconds. */
const WHILE_WORKING_MS = 4000

export function useIndexStatus() {
  const queryClient = useQueryClient()

  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: async () => {
      const status = await unwrap(await api.GET('/api/v1/admin/index/status'))
      // Huginn works in the background, so the library changes while this page is open. Whatever
      // shows albums and media has to follow along instead of waiting for a reload.
      if (isWorking(status)) void queryClient.invalidateQueries({ queryKey: ALBUMS_KEY })
      return status
    },
    refetchInterval: (query) =>
      query.state.data && isWorking(query.state.data) ? WHILE_WORKING_MS : false,
  })
}

/** Whether anything is still being read or derived right now. */
function isWorking(status: IndexStatus): boolean {
  return (
    status.publications.some((entry) => entry.last_sync_status === 'running') ||
    status.pending_metadata > 0 ||
    status.pending_derivatives > 0
  )
}

/** The folders the host has mounted, for picking one without typing a path. */
export function useFolders(path: string, enabled: boolean) {
  return useQuery({
    queryKey: [...BROWSE_KEY, path],
    enabled,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/admin/library/browse', { params: { query: { path } } })),
  })
}

export function usePublish() {
  const invalidate = useInvalidateLibrary()

  return useMutation({
    mutationFn: async (path: string) =>
      unwrap(await api.POST('/api/v1/admin/library/publications', { body: { path } })),
    onSuccess: invalidate,
  })
}

export function useUpdatePublication() {
  const invalidate = useInvalidateLibrary()

  return useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/library/publications/{publication_id}', {
          params: { path: { publication_id: id } },
          body: { enabled },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useUnpublish() {
  const invalidate = useInvalidateLibrary()

  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE('/api/v1/admin/library/publications/{publication_id}', {
          params: { path: { publication_id: id } },
        }),
      ),
    onSuccess: invalidate,
  })
}

/**
 * A subfolder of a published folder, switched off or on again. Off, its albums and media leave
 * Muninn; on, it is read again.
 */
export function useExclusion() {
  const invalidate = useInvalidateLibrary()

  return useMutation({
    mutationFn: async ({
      publicationId,
      path,
      published,
    }: {
      publicationId: string
      path: string
      published: boolean
    }) => {
      const params = { path: { publication_id: publicationId } }
      return unwrap(
        published
          ? await api.DELETE('/api/v1/admin/library/publications/{publication_id}/exclusions', {
              params: { ...params, query: { path } },
            })
          : await api.POST('/api/v1/admin/library/publications/{publication_id}/exclusions', {
              params,
              body: { relative_path: path },
            }),
      )
    },
    onSuccess: invalidate,
  })
}

export function useStartSync() {
  const invalidate = useInvalidateLibrary()

  return useMutation({
    mutationFn: async ({
      id,
      ...body
    }: {
      id: string
      quick?: boolean
      confirm_deletions?: boolean
    }) =>
      unwrap(
        await api.POST('/api/v1/admin/library/publications/{publication_id}/sync', {
          params: { path: { publication_id: id } },
          body: { quick: body.quick ?? false, confirm_deletions: body.confirm_deletions ?? false },
        }),
      ),
    onSuccess: invalidate,
  })
}

/**
 * Everything a change to the published folders touches.
 *
 * The admin area is not the only view of this: the album tree is built from the same rows, so
 * publishing, syncing or taking a folder back has to reach it too - otherwise the library looks
 * unchanged until somebody reloads the page.
 */
function useInvalidateLibrary() {
  const queryClient = useQueryClient()

  return () => {
    void queryClient.invalidateQueries({ queryKey: STATUS_KEY })
    void queryClient.invalidateQueries({ queryKey: BROWSE_KEY })
    void queryClient.invalidateQueries({ queryKey: ALBUMS_KEY })
    // Taking a folder back stops the work on it, so the engine room is out of date too.
    void queryClient.invalidateQueries({ queryKey: JOBS_KEY })
  }
}
