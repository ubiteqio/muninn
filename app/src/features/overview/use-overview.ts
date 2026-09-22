import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type Report = components['schemas']['ReportView']

/** The library at a glance. Cheap to ask; asked again when the page is opened. */
export function useOverview() {
  return useQuery({
    queryKey: ['overview'],
    queryFn: async () => unwrap(await api.GET('/api/v1/overview')),
  })
}
