import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import type { Medium } from '@/features/albums/use-albums'

export type PersonView = components['schemas']['PersonCard']
export type FaceView = components['schemas']['FaceView']
export type GroupView = components['schemas']['GroupView']
export type SuggestionView = components['schemas']['SuggestionView']
export type MediaFace = components['schemas']['MediaFaceView']

const KEY = ['people'] as const

/** Persons, the first unnamed groups, and how many suggestions wait. */
export function usePeople(hidden = false) {
  return useQuery({
    queryKey: [...KEY, 'overview', hidden],
    queryFn: async () => unwrap(await api.GET('/api/v1/people', { params: { query: { hidden } } })),
  })
}

export function useGroups() {
  return useInfiniteQuery({
    queryKey: [...KEY, 'groups'],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/people/groups', {
          params: { query: pageParam === null ? {} : { cursor: pageParam } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? null,
  })
}

export function useGroupFaces(cluster: number | null) {
  return useQuery({
    queryKey: [...KEY, 'group', cluster],
    enabled: cluster !== null,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/people/groups/{cluster}', {
          params: { path: { cluster: cluster ?? 0 } },
        }),
      ),
  })
}

export function useSuggestions(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: [...KEY, 'suggestions'],
    enabled,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/people/suggestions', {
          params: { query: pageParam === null ? {} : { cursor: pageParam } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? null,
  })
}

export function usePerson(personId: string) {
  return useQuery({
    queryKey: [...KEY, 'person', personId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/people/{person_id}', {
          params: { path: { person_id: personId } },
        }),
      ),
  })
}

export function usePersonMedia(personId: string) {
  const query = useInfiniteQuery({
    queryKey: ['media', 'person', personId],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/people/{person_id}/media', {
          params: {
            path: { person_id: personId },
            query: pageParam === null ? {} : { cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? null,
  })
  const media: Medium[] = query.data?.pages.flatMap((page) => page.items) ?? []
  return { ...query, media }
}

/** Which of a person's faces to check: given by Muninn, or twice in one photo. */
export type FaceFilter = components['schemas']['FaceFilter']

export function usePersonFaces(personId: string, only?: FaceFilter) {
  return useInfiniteQuery({
    queryKey: [...KEY, 'person', personId, 'faces', only ?? 'all'],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/people/{person_id}/faces', {
          params: {
            path: { person_id: personId },
            query: {
              ...(pageParam === null ? {} : { cursor: pageParam }),
              ...(only === undefined ? {} : { only }),
            },
          },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? null,
  })
}

export function useMediaFaces(mediaId: string | undefined) {
  return useQuery({
    queryKey: [...KEY, 'media', mediaId],
    enabled: mediaId !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/media/{media_id}/faces', {
          params: { path: { media_id: mediaId ?? '' } },
        }),
      ),
  })
}

/** Everything that may show a person again: the screens here, and the photos. */
function useRefresh() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: KEY }),
      queryClient.invalidateQueries({ queryKey: ['media'] }),
    ])
}

export function useNameGroup() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async ({ cluster, name }: { cluster: number; name: string }) =>
      unwrap(
        await api.POST('/api/v1/people/groups/{cluster}/name', {
          params: { path: { cluster } },
          body: { name },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useAnswer() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async ({ faceId, yes }: { faceId: string; yes: boolean }) => {
      const params = { params: { path: { face_id: faceId } } }
      await unwrap(
        yes
          ? await api.POST('/api/v1/faces/{face_id}/confirm', params)
          : await api.POST('/api/v1/faces/{face_id}/reject', params),
      )
    },
    onSuccess: refresh,
  })
}

export function useNameFace() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async ({ faceId, name }: { faceId: string; name: string }) =>
      unwrap(
        await api.POST('/api/v1/faces/{face_id}/name', {
          params: { path: { face_id: faceId } },
          body: { name },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useUpdatePerson(personId: string) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async (change: { name?: string; hidden?: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/people/{person_id}', {
          params: { path: { person_id: personId } },
          body: change,
        }),
      ),
    onSuccess: refresh,
  })
}

export function useMerge(personId: string) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async (into: string) =>
      unwrap(
        await api.POST('/api/v1/people/{person_id}/merge', {
          params: { path: { person_id: personId } },
          body: { into },
        }),
      ),
    onSuccess: refresh,
  })
}
