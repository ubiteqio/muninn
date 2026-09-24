import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { onLiveEvent } from '@/api/live'
import type { Medium } from '@/features/albums/use-albums'

export type PersonView = components['schemas']['PersonCard']
export type FaceView = components['schemas']['FaceView']
export type GroupView = components['schemas']['GroupView']
export type SuggestionView = components['schemas']['SuggestionView']
export type MediaFace = components['schemas']['MediaFaceView']
export type AlikeFace = components['schemas']['AlikeFace']

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

/**
 * Stand by what Muninn decided for a whole page of faces at once.
 *
 * A face Muninn assigned itself vouches for nobody when the next face is sorted - one wrong
 * guess would otherwise teach the rest - so a person may have thousands of faces and still be
 * recognised poorly. Going through them a page at a time, taking the wrong ones out with the
 * cross and standing by the rest, is what turns those conclusions into evidence.
 */
export function useConfirmMany(personId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (faceIds: string[]) =>
      unwrap(await api.POST('/api/v1/faces/confirm', { body: { face_ids: faceIds } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...KEY, 'person', personId] })
      void queryClient.invalidateQueries({ queryKey: KEY })
    },
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

/**
 * The open questions about the same person that look like the one just answered.
 *
 * Asked once, at the widest distance the server offers, and narrowed in the browser: the slider
 * in the dialog then costs nothing to move.
 */
export function useAlikeFaces(faceId: string | null, personId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'alike', faceId, personId],
    enabled: faceId !== null && personId !== null,
    // The answer is about one moment; asking again later would be a different list.
    staleTime: Infinity,
    gcTime: 60_000,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/faces/{face_id}/alike', {
          params: { path: { face_id: faceId ?? '' }, query: { person: personId ?? '' } },
        }),
      ),
  })
}

/** The same yes or no for a whole list of faces. */
export function useDecideAlike() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async ({
      personId,
      faceIds,
      yes,
    }: {
      personId: string
      faceIds: string[]
      yes: boolean
    }) =>
      unwrap(
        await api.POST('/api/v1/faces/alike', {
          body: { person_id: personId, face_ids: faceIds, confirm: yes },
        }),
      ),
    onSuccess: refresh,
  })
}

/**
 * Keeps the Personen screen in step with the worker.
 *
 * The pass that looks at the faces again answers questions by itself. Without this the screen
 * would still be offering them minutes later, and somebody would be deciding what was decided.
 */
export function useLivePeople(): void {
  const queryClient = useQueryClient()

  useEffect(
    () =>
      onLiveEvent((event) => {
        if (event.topic !== 'people') return
        void queryClient.invalidateQueries({ queryKey: KEY })
      }),
    [queryClient],
  )
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
