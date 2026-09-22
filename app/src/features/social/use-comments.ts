import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { socialKey, type SocialTarget } from '@/features/social/use-social'

export type Comment = components['schemas']['CommentView']
export type Person = components['schemas']['PersonView']

export const commentsKey = (target: SocialTarget) => ['comments', target.kind, target.id] as const

/** Every comment of a medium or album, answers under what they answer. */
export function useComments(target: SocialTarget, enabled = true) {
  return useQuery({
    queryKey: commentsKey(target),
    enabled,
    queryFn: async () => {
      if (target.kind === 'media') {
        return unwrap(
          await api.GET('/api/v1/media/{media_id}/comments', {
            params: { path: { media_id: target.id } },
          }),
        )
      }
      return unwrap(
        await api.GET('/api/v1/albums/{album_id}/comments', {
          params: { path: { album_id: target.id } },
        }),
      )
    },
  })
}

/** After any change: the conversation and the number beside the speech bubble. */
function useRefresh(target: SocialTarget) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: commentsKey(target) })
    void queryClient.invalidateQueries({ queryKey: socialKey(target) })
  }
}

export function useAddComment(target: SocialTarget) {
  const refresh = useRefresh(target)
  return useMutation({
    mutationFn: async ({ body, parentId }: { body: string; parentId?: string | undefined }) => {
      const payload = { body, ...(parentId ? { parent_id: parentId } : {}) }
      if (target.kind === 'media') {
        return unwrap(
          await api.POST('/api/v1/media/{media_id}/comments', {
            params: { path: { media_id: target.id } },
            body: payload,
          }),
        )
      }
      return unwrap(
        await api.POST('/api/v1/albums/{album_id}/comments', {
          params: { path: { album_id: target.id } },
          body: payload,
        }),
      )
    },
    onSuccess: refresh,
  })
}

export function useEditComment(target: SocialTarget) {
  const refresh = useRefresh(target)
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: string }) =>
      unwrap(
        await api.PATCH('/api/v1/comments/{comment_id}', {
          params: { path: { comment_id: id } },
          body: { body },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useDeleteComment(target: SocialTarget) {
  const refresh = useRefresh(target)
  return useMutation({
    mutationFn: async (id: string) => {
      // 204 carries nothing; unwrap still turns a refusal into the problem it is.
      await unwrap(
        await api.DELETE('/api/v1/comments/{comment_id}', {
          params: { path: { comment_id: id } },
        }),
      )
    },
    onSuccess: refresh,
  })
}

export function useLikeComment(target: SocialTarget) {
  const refresh = useRefresh(target)
  return useMutation({
    mutationFn: async ({ id, on }: { id: string; on: boolean }) => {
      const params = { params: { path: { comment_id: id } } }
      return unwrap(
        on
          ? await api.POST('/api/v1/comments/{comment_id}/like', params)
          : await api.DELETE('/api/v1/comments/{comment_id}/like', params),
      )
    },
    onSuccess: refresh,
  })
}

/** Who can be named with @ - asked once, kept for a while. */
export function usePeople() {
  return useQuery({
    queryKey: ['people', 'mentionable'],
    staleTime: 5 * 60_000,
    queryFn: async () => unwrap(await api.GET('/api/v1/people/mentionable')),
  })
}
