import { useInfiniteQuery } from '@tanstack/react-query'
import type { TFunction } from 'i18next'

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

/**
 * What a chapter is called, in German.
 *
 * The server keeps a key and its values - "trip", {place: "Chessy", days: 4} - and never a
 * sentence: a name written there would be German in the database, where no text of the app
 * belongs. The app turns it into "Vier Tage Chessy", and a second language would only need
 * another file of texts.
 */
export function titleOf(chapter: Chapter, t: TFunction): string {
  const args = chapter.title_args
  // The values are what the server put there: numbers, dates and names, never objects.
  const value = (name: string): string => {
    const found = args[name]
    return typeof found === 'string' || typeof found === 'number' ? String(found) : ''
  }

  switch (chapter.title_key) {
    case 'trip':
      return t('smarts.name.trip', { count: Number(args.days ?? 0), place: value('place') })
    case 'day':
      return [dayOf(value('day')), value('place')].filter(Boolean).join(' · ')
    case 'place':
      return t('smarts.name.place', {
        place: value('place'),
        span: yearsOf(Number(args.from), Number(args.until)),
      })
    case 'person':
      return t('smarts.name.person', { name: value('name'), year: value('year') })
    case 'pair':
      return t('smarts.name.pair', { first: value('first'), second: value('second') })
    case 'christmas':
    case 'newyear':
      return t(`smarts.name.${chapter.title_key}`, { count: Number(args.years ?? 0) })
    default:
      return value('words') || t('smarts.unnamed')
  }
}

/** A day as it is written here: "3. Mai 2016". */
function dayOf(iso: string): string {
  const [year, month, day] = iso.split('-')
  const name = MONTHS[Number(month) - 1]
  return name ? `${String(Number(day))}. ${name} ${year ?? ''}`.trim() : iso
}

function yearsOf(from: number, until: number): string {
  if (!from) return ''
  return from === until ? String(from) : `${String(from)}–${String(until)}`
}

const MONTHS = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
]

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
