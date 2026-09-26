import { useInfiniteQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'

export type Chapter = components['schemas']['ChapterView']
export type Shelf = components['schemas']['ShelfView']
export type FaceStrip = components['schemas']['FaceStripView']
export type Medium = components['schemas']['MediaView']

const PAGE_SIZE = 24

/**
 * What the library falls into: chapters, shelves and the faces that turn up most.
 *
 * None of it asks a machine. The groups were found by a worker from vectors that are in the
 * database anyway, so the Smarts are there while the AI machine is switched off - which is
 * exactly when somebody sits down to browse.
 */
export function useSmarts() {
  return useInfiniteQuery({
    queryKey: ['smarts'],
    initialPageParam: 0,
    getNextPageParam: (last: components['schemas']['SmartsView']) => last.next_offset ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/smarts', {
          params: { query: { offset: pageParam, limit: PAGE_SIZE } },
        }),
      ),
  })
}

/** One chapter and its media, the clearest examples first. */
export function useChapter(chapterId: string | undefined) {
  return useInfiniteQuery({
    queryKey: ['smarts', 'chapter', chapterId ?? ''],
    enabled: chapterId !== undefined,
    initialPageParam: 0,
    getNextPageParam: (last: components['schemas']['ChapterMediaList']) =>
      last.next_offset ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/smarts/chapters/{chapter_id}', {
          params: { path: { chapter_id: chapterId ?? '' }, query: { offset: pageParam } },
        }),
      ),
  })
}

/** One shelf: videos, documents, screenshots - everything with one trait, newest first. */
export function useShelf(key: string | undefined) {
  return useInfiniteQuery({
    queryKey: ['smarts', 'shelf', key ?? ''],
    enabled: key !== undefined,
    initialPageParam: 0,
    getNextPageParam: (last: components['schemas']['ShelfMediaList']) =>
      last.next_offset ?? undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/smarts/shelves/{key}', {
          params: { path: { key: key ?? '' }, query: { offset: pageParam } },
        }),
      ),
  })
}

/** Everything the app has fetched so far, as one list. */
export function pagesOf<T>(pages: { items: T[] }[] | undefined): T[] {
  return (pages ?? []).flatMap((page) => page.items)
}

export function chaptersOf(pages: components['schemas']['SmartsView'][] | undefined): Chapter[] {
  return (pages ?? []).flatMap((page) => page.chapters)
}

/** How long a chapter covers, as "09.2017 – 10.2019", or one month when it is one.
 *
 * Written out rather than left to the browser's own month format: the app is German wherever it
 * runs, and a date that reads differently on a phone than on a laptop is a date nobody trusts.
 */
export function spanOf(chapter: Chapter): string {
  if (!chapter.from_at) return ''
  const month = (value: string) => `${value.slice(5, 7)}.${value.slice(0, 4)}`
  const first = month(chapter.from_at)
  const last = chapter.until_at ? month(chapter.until_at) : first
  return first === last ? first : `${first} – ${last}`
}
