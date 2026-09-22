import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { ABILITIES_KEY } from '@/features/search/use-search'

export type AiProfile = components['schemas']['AiProfileView']
export type AiKind = components['schemas']['AiKind']
export type AiCheck = components['schemas']['AiCheckView']
export type AiProfileCreate = components['schemas']['AiProfileCreate']
export type AiProfileUpdate = components['schemas']['AiProfileUpdate']

export const AI_KEY = ['admin', 'ai', 'profiles'] as const

/** The three interfaces, in the order the pipeline uses them. */
export const AI_KINDS: AiKind[] = [
  'image_embedder',
  'analyzer',
  'text_embedder',
  'transcriber',
  'face_detector',
]

/** The profiles, and what the search can look into - which a new or removed model changes. */
function refreshAfterChange(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: AI_KEY }),
    queryClient.invalidateQueries({ queryKey: ABILITIES_KEY }),
  ])
}

export function useAiProfiles() {
  return useQuery({
    queryKey: AI_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/ai/profiles')),
  })
}

export function useCreateAiProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (profile: AiProfileCreate) =>
      unwrap(await api.POST('/api/v1/admin/ai/profiles', { body: profile })),
    onSuccess: () => refreshAfterChange(queryClient),
  })
}

export function useSaveAiProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, changes }: { id: string; changes: AiProfileUpdate }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/ai/profiles/{profile_id}', {
          params: { path: { profile_id: id } },
          body: changes,
        }),
      ),
    onSuccess: () => refreshAfterChange(queryClient),
  })
}

export function useActivateAiProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/admin/ai/profiles/{profile_id}/activate', {
          params: { path: { profile_id: id } },
        }),
      ),
    onSuccess: () => refreshAfterChange(queryClient),
  })
}

export function useRemoveAiProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE('/api/v1/admin/ai/profiles/{profile_id}', {
          params: { path: { profile_id: id } },
        }),
      ),
    onSuccess: () => refreshAfterChange(queryClient),
  })
}

/** Ask one machine whether it is there. The answer is shown as it comes, and not remembered. */
export function useTestAiProfile() {
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/admin/ai/profiles/{profile_id}/test', {
          params: { path: { profile_id: id } },
        }),
      ),
  })
}
