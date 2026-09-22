import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type AppSettings = components['schemas']['SettingsView']
export type SettingsUpdate = components['schemas']['SettingsUpdate']

const SETTINGS_KEY = ['admin', 'settings'] as const

export function useSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/settings')),
  })
}

/** The endpoint is a PUT: it takes every setting, not the ones that changed. */
export function useSaveSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: SettingsUpdate) =>
      unwrap(await api.PUT('/api/v1/admin/settings', { body: input })),
    onSuccess: (settings) => {
      queryClient.setQueryData(SETTINGS_KEY, settings)
    },
  })
}
