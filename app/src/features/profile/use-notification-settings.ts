import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type NotificationSettings = components['schemas']['NotificationSettingsView']

const KEY = ['me', 'notification-settings'] as const

export function useNotificationSettings() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/me/notification-settings')),
  })
}

/** Every change is saved as it is made; the answer is what the server kept. */
export function useSaveNotificationSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (settings: NotificationSettings) =>
      unwrap(await api.PUT('/api/v1/me/notification-settings', { body: settings })),
    onMutate: (settings) => {
      queryClient.setQueryData(KEY, settings)
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(KEY, saved)
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: KEY })
    },
  })
}
