import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type DuplicateGroup = components['schemas']['DuplicateGroupView']
export type DuplicateState = 'open' | 'all'
/** Newest first, or the groups that hold the most disk first. */
export type DuplicateSort = 'newest' | 'size'

const KEY = ['admin', 'duplicates'] as const

/** The groups of copies, page by page: newest first, or heaviest first. */
export function useDuplicates(state: DuplicateState, sort: DuplicateSort = 'newest') {
  return useInfiniteQuery({
    queryKey: [...KEY, state, sort],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/admin/duplicates', {
          params: {
            query: { state, sort, ...(pageParam === null ? {} : { cursor: pageParam }) },
          },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? null,
  })
}

/** Keep these members of a group, hide the rest - and every list that showed them learns it. */
export function useKeep() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ groupId, keep }: { groupId: number; keep: string[] }) =>
      unwrap(
        await api.POST('/api/v1/admin/duplicates/{group_id}/keep', {
          params: { path: { group_id: groupId } },
          body: { media_ids: keep },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: KEY }),
        queryClient.invalidateQueries({ queryKey: ['albums'] }),
        queryClient.invalidateQueries({ queryKey: ['media'] }),
      ]),
  })
}

export function useShowAgain() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (mediaId: string) =>
      unwrap(
        await api.DELETE('/api/v1/admin/duplicates/hidden/{media_id}', {
          params: { path: { media_id: mediaId } },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: KEY }),
        queryClient.invalidateQueries({ queryKey: ['albums'] }),
        queryClient.invalidateQueries({ queryKey: ['media'] }),
      ]),
  })
}

/** The paths of every hidden copy as a CSV file, saved by the browser. Muninn deletes nothing. */
export async function downloadHiddenList(): Promise<void> {
  const { data, response } = await api.GET('/api/v1/admin/duplicates/hidden.csv', {
    parseAs: 'text',
  })
  if (!response.ok || data === undefined) throw new Error(`hidden list: ${String(response.status)}`)
  const url = URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'muninn-duplikate.csv'
  link.click()
  URL.revokeObjectURL(url)
}
