import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { onLiveEvent } from '@/api/live'
import { getAccessToken } from '@/api/session'
import type { Reaction } from '@/features/social/reactions'

export type Social = components['schemas']['SocialView']
export type SocialKind = 'media' | 'album'

export interface SocialTarget {
  kind: SocialKind
  id: string
}

export const socialKey = (target: SocialTarget) => ['social', target.kind, target.id] as const

/** Likes and favourite of one medium or album, for the heart and the star. */
export function useSocial(target: SocialTarget | undefined) {
  return useQuery({
    queryKey: target ? socialKey(target) : ['social', 'none'],
    enabled: target !== undefined,
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<Social> => {
      if (!target) throw new Error('no target')
      if (target.kind === 'media') {
        return unwrap(
          await api.GET('/api/v1/media/{media_id}/social', {
            params: { path: { media_id: target.id } },
          }),
        )
      }
      return unwrap(
        await api.GET('/api/v1/albums/{album_id}/social', {
          params: { path: { album_id: target.id } },
        }),
      )
    },
  })
}

/**
 * The heart - or, on a medium, any reaction: true is a heart, a reaction's name that one, false
 * takes it back. The answer is the new state, so the page shows it without asking again.
 */
export function useToggleLike(target: SocialTarget | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (on: boolean | Reaction): Promise<Social> => {
      if (!target) throw new Error('no target')
      if (target.kind === 'media') {
        const params = { params: { path: { media_id: target.id } } }
        if (on === false) return unwrap(await api.DELETE('/api/v1/media/{media_id}/like', params))
        return unwrap(
          await api.POST('/api/v1/media/{media_id}/like', {
            ...params,
            body: { reaction: on === true ? 'heart' : on },
          }),
        )
      }
      const params = { params: { path: { album_id: target.id } } }
      return unwrap(
        on
          ? await api.POST('/api/v1/albums/{album_id}/like', params)
          : await api.DELETE('/api/v1/albums/{album_id}/like', params),
      )
    },
    onSuccess: (social) => {
      if (!target) return
      queryClient.setQueryData(socialKey(target), social)
      // The info panel reads the same from the medium's detail.
      if (target.kind === 'media')
        void queryClient.invalidateQueries({ queryKey: ['media', target.id] })
    },
  })
}

/** The star: into Walhall and out again. */
export function useToggleFavorite(target: SocialTarget | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (on: boolean): Promise<Social> => {
      if (!target) throw new Error('no target')
      const body = target.kind === 'media' ? { media_id: target.id } : { album_id: target.id }
      return unwrap(
        on
          ? await api.POST('/api/v1/favorites', { body })
          : await api.DELETE('/api/v1/favorites', { body }),
      )
    },
    onSuccess: (social) => {
      if (!target) return
      queryClient.setQueryData(socialKey(target), social)
      void queryClient.invalidateQueries({ queryKey: ['favorites'] })
    },
  })
}

/**
 * Hearts others give arrive while one looks: the server announces every like on the live
 * channel, and the heart of that medium or album is read again.
 */
export function useSocialUpdates(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!getAccessToken()) return
    return onLiveEvent((event) => {
      if (event.topic !== 'social') return
      const kind = event.target === 'album' ? 'album' : 'media'
      const id = typeof event.id === 'string' ? event.id : undefined
      if (!id) return
      void queryClient.invalidateQueries({ queryKey: socialKey({ kind, id }) })
      if (event.kind === 'comments') {
        void queryClient.invalidateQueries({ queryKey: ['comments', kind, id] })
      }
      if (kind === 'media') void queryClient.invalidateQueries({ queryKey: ['media', id] })
    })
  }, [queryClient])
}

const FAVORITES_PAGE = 60

/** Walhall's pictures and videos, page after page, the most recently kept first. */
export function useFavoriteMedia(limit = FAVORITES_PAGE) {
  return useInfiniteQuery({
    queryKey: ['favorites', 'media', limit],
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: { next_cursor?: string | null }) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/favorites/media', {
          params: { query: { limit, ...(pageParam ? { before: pageParam } : {}) } },
        }),
      ),
  })
}

/** Walhall's albums. */
export function useFavoriteAlbums() {
  return useQuery({
    queryKey: ['favorites', 'albums'],
    queryFn: async () => unwrap(await api.GET('/api/v1/favorites/albums')),
  })
}
