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

/** What one save changes about an account; whatever is left out stays as it is. */
export interface AccountChanges {
  role?: UserRole
  status?: UserStatus
  display_name?: string
  username?: string
  /** An empty string takes the address away. */
  email?: string
  /** A new password; the user picks their own at the next sign-in. */
  password?: string
  /** The person on the photos who signs in with this account, or null for nobody. */
  person_id?: string | null
}

export function useUpdateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...changes }: AccountChanges & { id: string }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/users/{user_id}', {
          params: { path: { user_id: id } },
          body: changes,
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: USERS_KEY }),
        // The person page shows whom a person signs in as.
        queryClient.invalidateQueries({ queryKey: ['people'] }),
      ]),
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
