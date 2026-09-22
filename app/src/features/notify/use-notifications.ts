import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import type { useTranslation } from 'react-i18next'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { onLiveEvent } from '@/api/live'
import { getAccessToken } from '@/api/session'

export type Notice = components['schemas']['NotificationView']
export type Happening = components['schemas']['ActivityView']

/** The number on the bell. */
export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: async () => unwrap(await api.GET('/api/v1/notifications/unread')),
  })
}

/** The bell's list, asked for only while it is open. */
export function useNotifications(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ['notifications', 'list'],
    enabled,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: { next_cursor?: string | null }) => last.next_cursor ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/notifications', {
          params: { query: pageParam ? { before: pageParam } : {} },
        }),
      ),
  })
}

/** Everything read - what opening the bell means. */
export function useMarkAllRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await unwrap(await api.POST('/api/v1/notifications/read', { body: {} }))
    },
    onSuccess: () => {
      queryClient.setQueryData(['notifications', 'unread'], { count: 0 })
    },
  })
}

/** What everybody has been doing, for the start page. */
export function useActivity(limit = 8) {
  return useQuery({
    queryKey: ['activity', limit],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/activity', { params: { query: { limit } } })),
  })
}

/**
 * The bell and the news follow the live channel: a ping for me moves the bell, anything
 * anybody does refreshes the news.
 */
/** How long news wait for more of their kind before the list is asked for again. */
const NEWS_BUNDLE_MS = 3000

export function useNoticeUpdates(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!getAccessToken()) return
    // The news follow everybody's doing; a burst of it is one request, not one per event.
    let news: ReturnType<typeof setTimeout> | undefined
    const stop = onLiveEvent((event) => {
      if (event.topic === 'notifications') {
        void queryClient.invalidateQueries({ queryKey: ['notifications'] })
      }
      const newsWorthy =
        event.topic === 'notifications' || event.topic === 'social' || event.topic === 'library'
      if (newsWorthy && news === undefined) {
        news = setTimeout(() => {
          news = undefined
          void queryClient.invalidateQueries({ queryKey: ['activity'] })
        }, NEWS_BUNDLE_MS)
      }
    })
    return () => {
      stop()
      clearTimeout(news)
    }
  }, [queryClient])
}

type Translate = ReturnType<typeof useTranslation>['t']

/** "Anna", "Anna und Boris", "Anna und 2 weitere". */
export function people(names: string[], count: number, t: Translate): string {
  const [first, second] = names
  if (!first) return ''
  const others = Math.max(count, names.length) - 1
  if (others === 0) return first
  if (others === 1 && second) return t('notify.two', { first, second })
  return t('notify.more', { first, count: others })
}
