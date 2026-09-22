import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { onLiveEvent } from '@/api/live'

export type Jobs = components['schemas']['JobsView']
export type Change = components['schemas']['ChangeView']
export type RunningRead = components['schemas']['RunningRead']
export type ActiveTask = components['schemas']['ActiveTask']
export type FinishedTask = components['schemas']['FinishedTask']

export const JOBS_KEY = ['admin', 'jobs'] as const

export type AiService = components['schemas']['AiServiceView']

/**
 * Asked on a clock of its own, not with the jobs: the server keeps each answer for half a
 * minute, so asking more often gains nothing - and a key outside ['admin', 'jobs'] keeps the
 * live events of the pipeline from asking again with every finished medium.
 */
const AI_HEALTH_MS = 30_000

/** Ends a stage's pause: the machine is back, the admin says so. */
export function useResumeAi() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (kind: AiService['kind']) =>
      unwrap(
        await api.DELETE('/api/v1/admin/jobs/ai/{kind}/pause', {
          // The chip carries the kind as the server named it; only the interfaces there are.
          params: { path: { kind: kind as components['schemas']['AiKind'] } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'ai-health'] }),
  })
}

export function useAiHealth() {
  return useQuery({
    queryKey: ['admin', 'ai-health'],
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/jobs/ai')),
    refetchInterval: AI_HEALTH_MS,
  })
}

/**
 * Asking is only the safety net now: the live channel says when something happened, and this
 * keeps the page honest if the socket is closed or an event was missed.
 */
const WHILE_BUSY_MS = 5000
const WHILE_IDLE_MS = 15000

/**
 * A worker finishes a medium about every eighty milliseconds. Reading the whole picture after
 * each one would be a dozen requests a second, so events are collected for this long and
 * answered with one.
 */
const COALESCE_MS = 400

export function useJobs() {
  return useQuery({
    queryKey: ['admin', 'jobs'],
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/jobs')),
    refetchInterval: (query) =>
      query.state.data && isBusy(query.state.data) ? WHILE_BUSY_MS : WHILE_IDLE_MS,
  })
}

/**
 * Keeps the engine room in step with what actually happens.
 *
 * The event itself carries no names - it says that something is through, and the page asks for
 * the picture that goes with it. One source of truth, and no flood: a burst of events becomes
 * one request.
 */
export function useLiveJobs(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    let pending: ReturnType<typeof setTimeout> | null = null

    const stop = onLiveEvent((event) => {
      if (event.topic !== 'jobs' || pending) return
      pending = setTimeout(() => {
        pending = null
        void queryClient.invalidateQueries({ queryKey: JOBS_KEY })
        void queryClient.invalidateQueries({ queryKey: CHANGES_KEY })
      }, COALESCE_MS)
    })

    return () => {
      if (pending) clearTimeout(pending)
      stop()
    }
  }, [queryClient])
}

/** The last findings of the syncs, newest first. */
export const CHANGES_KEY = ['admin', 'changes'] as const

export function useChanges(limit = 20) {
  return useQuery({
    queryKey: [...CHANGES_KEY, limit],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/admin/index/changes', { params: { query: { limit } } })),
    refetchInterval: WHILE_IDLE_MS,
  })
}

export function isBusy(jobs: Jobs): boolean {
  return (
    jobs.running.length > 0 ||
    jobs.active.length > 0 ||
    jobs.queues.some((queue) => queue.waiting > 0) ||
    jobs.pending_metadata > 0 ||
    jobs.pending_derivatives > 0 ||
    jobs.waiting_files > 0
  )
}

/** Stopping a read. It stops between folders, so what it already read is kept. */
export function useStopRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (publicationId: string) =>
      unwrap(
        await api.DELETE('/api/v1/admin/jobs/reads/{publication_id}', {
          params: { path: { publication_id: publicationId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: JOBS_KEY }),
  })
}

/** Stopping one piece of work, ffmpeg and all. */
export function useStopTask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (taskId: string) =>
      unwrap(
        await api.DELETE('/api/v1/admin/jobs/active/{task_id}', {
          params: { path: { task_id: taskId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: JOBS_KEY }),
  })
}

/** Emptying a queue. Nothing is lost: the next read queues what is still missing. */
export function usePurgeQueue() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(await api.DELETE('/api/v1/admin/jobs/queues/{name}', { params: { path: { name } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: JOBS_KEY }),
  })
}
