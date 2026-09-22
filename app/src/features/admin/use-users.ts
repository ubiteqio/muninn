import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type User = components['schemas']['UserProfile']
export type UserRole = components['schemas']['UserRole']
export type UserStatus = components['schemas']['UserStatus']

const USERS_KEY = ['admin', 'users'] as const

/**
 * The account list, page by page. Cursor pagination, because page numbers get slow once a list is
 * long - the same rule the whole API follows.
 */
export function useUsers() {
  return useInfiniteQuery({
    queryKey: USERS_KEY,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/admin/users', {
          params: { query: pageParam === null ? {} : { cursor: pageParam } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: { username: string; display_name: string; role: UserRole }) =>
      unwrap(await api.POST('/api/v1/admin/users', { body: input })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      ...changes
    }: {
      id: string
      role?: UserRole
      status?: UserStatus
      display_name?: string
      username?: string
      /** An empty string takes the address away. */
      email?: string
    }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/users/{user_id}', {
          params: { path: { user_id: id } },
          body: changes,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  })
}

export function useResetPassword() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/admin/users/{user_id}/password', {
          params: { path: { user_id: id } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  })
}

/** Remove an account for good, with its likes, favourites, comments and notifications. */
export function useDeleteUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await unwrap(
        await api.DELETE('/api/v1/admin/users/{user_id}', { params: { path: { user_id: id } } }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  })
}
