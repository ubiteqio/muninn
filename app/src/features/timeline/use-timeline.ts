import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import type { Medium } from '@/features/albums/use-albums'

export type TimelineShape = components['schemas']['TimelineShapeView']
export type Mark = components['schemas']['MarkView']
export type Period = components['schemas']['PeriodView']

/** How far away the timeline is looked at. The address carries this word. */
export type Level = 'years' | 'months' | 'days'

/** How finely the counts are cut. The same words the server uses. */
export type Granularity = 'year' | 'month' | 'day'

/** The key of a slice, as long as its granularity: "2014", "2014-08", "2014-08-28". */
const KEY_LENGTH: Record<Granularity, number> = { year: 4, month: 7, day: 10 }

export function keyOf(shape: TimelineShape, mark: Mark): string {
  return mark.start.slice(0, KEY_LENGTH[shape.by])
}

/** One request, and the window that travels the timeline is three of them. */
export const PAGE_SIZE = 100
const WINDOW_PAGES = 3

/**
 * The shape of the timeline at one distance: how much every year, month or day holds.
 *
 * Everything the timeline knows about the parts it has not loaded - how tall they are, which
 * moment a position points at - comes from here. Even by day this stays small: only days with
 * media are in it, which for a family library is a few thousand rows once, then cached.
 */
export function useTimelineShape(by: Granularity = 'month', year?: number) {
  return useQuery({
    queryKey: ['timeline', 'shape', by, year ?? null],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/media/marks', {
          params: { query: { by, ...(year === undefined ? {} : { year }) } },
        }),
      ),
  })
}

/**
 * The cards of an overview: every year of the library, or every month of one year.
 *
 * Counts and a few pictures per period, in two queries - the level knows what it holds before
 * anybody scrolls, and a year with eight hundred photos costs as much as one with eight.
 */
export function usePeriods(by: 'year' | 'month', year?: number) {
  return useQuery({
    queryKey: ['timeline', 'periods', by, year ?? null],
    // The cards of the level before stay until the new ones are here. A grid that empties out
    // and fills again is a page that jumps under the hand that just tapped it.
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/media/periods', {
          params: { query: { by, ...(year === undefined ? {} : { year }) } },
        }),
      ),
  })
}

interface PageParam {
  cursor?: string
  before?: string
  at?: string
}

/**
 * The window of media that is actually loaded inside one month.
 *
 * `maxPages` is what makes it a window rather than a list that only grows: walking into the past
 * drops the pages behind, walking back drops the pages ahead. At three pages the document holds
 * a few hundred tiles however far one travels, and the spacers above and below stand in for the
 * rest of the library.
 */
export function useTimelineWindow(month: string, anchor: string | null) {
  // Named rather than inlined: the type of this is the type of every page parameter after it.
  const start: PageParam = anchor === null ? {} : { at: anchor }

  return useInfiniteQuery({
    queryKey: ['timeline', 'window', month, anchor],
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/media', {
          params: { query: { limit: PAGE_SIZE, month, ...pageParam } },
        }),
      ),
    initialPageParam: start,
    getNextPageParam: (last): PageParam | undefined => {
      const cursor = last.next_cursor ?? null
      return cursor === null ? undefined : { cursor }
    },
    getPreviousPageParam: (first): PageParam | undefined => {
      const before = first.prev_cursor ?? null
      return before === null ? undefined : { before }
    },
    maxPages: WINDOW_PAGES,
  })
}

export interface TimelineGroup {
  /** The slice, as "2014-08-28", or "undated" for media whose date nobody knows yet. */
  id: string
  label: string
  /** Every date in here was guessed, from a folder name or the file's own time. */
  estimated: boolean
  media: Medium[]
}

/**
 * The loaded media, cut into months.
 *
 * Cut rather than sorted: the server hands them over in order, so a new month simply begins
 * where the date changes.
 */
export function groupBy(media: Medium[], by: Granularity, undatedLabel: string): TimelineGroup[] {
  const groups: TimelineGroup[] = []

  for (const medium of media) {
    const id = medium.taken_at === null ? 'undated' : medium.taken_at.slice(0, KEY_LENGTH[by])
    const last = groups.at(-1)
    if (last?.id === id) {
      last.media.push(medium)
      continue
    }
    groups.push({
      id,
      label: id === 'undated' ? undatedLabel : labelOf(id),
      estimated: false,
      media: [medium],
    })
  }

  // Said once above the day rather than on every picture in it: a folder called "2010" gives
  // every file in it the same guess, and writing that over each photo buries the photos.
  return groups.map((group) => ({
    ...group,
    estimated: group.media.every((medium) => medium.date_is_estimated),
  }))
}

/** "2014" as "2014", "2014-08" as "August 2014", "2014-08-28" as "Do., 28. August 2014". */
export function labelOf(key: string): string {
  if (key.length === 4) return key

  const date = new Date(key.length === 7 ? `${key}-01T00:00:00Z` : `${key}T00:00:00Z`)
  const parts: Intl.DateTimeFormatOptions =
    key.length === 7
      ? { month: 'long', year: 'numeric' }
      : { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }
  return date.toLocaleDateString('de-DE', { ...parts, timeZone: 'UTC' })
}

/** How many media lie above this slice, that is: were taken later than it. */
export function countAbove(shape: TimelineShape, key: string): number {
  let above = 0
  for (const mark of shape.marks) {
    if (keyOf(shape, mark) <= key) break
    above += mark.count
  }
  return above
}

/**
 * Which moment a position on the rail points at, as an ISO date.
 *
 * The rail is divided by how much each month holds, not by how long it lasted: a summer with
 * five hundred photos takes more of it than a winter with none, which is where a finger expects
 * to find them.
 */
export function momentAt(shape: TimelineShape, progress: number): string | null {
  if (shape.total === 0) return null

  const wanted = Math.min(Math.max(progress, 0), 1) * shape.total
  let passed = 0
  for (const mark of shape.marks) {
    passed += mark.count
    if (passed >= wanted) return endOf(mark.start, shape.by)
  }
  const last = shape.marks.at(-1)
  return last ? endOf(last.start, shape.by) : null
}

/**
 * Put the page at this height.
 *
 * `scrollTo` is the method for it, but it does not exist everywhere a component is rendered -
 * jsdom has no layout and no such method - and a timeline that throws where it cannot scroll
 * would take the whole screen with it.
 */
export function scrollPageTo(container: HTMLElement, top: number): void {
  if (typeof container.scrollTo === 'function') container.scrollTo({ top })
  else container.scrollTop = top
}

export interface Geometry {
  /** How many tiles sit in a row. */
  columns: number
  /** A row of tiles plus the gap below it. */
  rowHeight: number
  /** The month heading above each group. */
  heading: number
}

/** How tall a run of months is when drawn in this grid. */
function heightOf(marks: Mark[], geometry: Geometry): number {
  return marks.reduce(
    (height, mark) =>
      height + Math.ceil(mark.count / geometry.columns) * geometry.rowHeight + geometry.heading,
    0,
  )
}

/** The slices above this one - those taken later - as the height they would take up. */
export function heightAbove(shape: TimelineShape, key: string, geometry: Geometry): number {
  return heightOf(
    shape.marks.filter((mark) => keyOf(shape, mark) > key),
    geometry,
  )
}

/** And the slices below it, at the older end. */
export function heightBelow(shape: TimelineShape, key: string, geometry: Geometry): number {
  return heightOf(
    shape.marks.filter((mark) => keyOf(shape, mark) < key),
    geometry,
  )
}

/**
 * How tall the whole timeline is, down to the last month.
 *
 * Nothing but the month counts is needed for this, so the page is as long as the library from
 * the first frame - the scrollbar means something, and every position on it points at a date.
 */
export function heightOfAll(shape: TimelineShape, geometry: Geometry): number {
  return heightOf(shape.marks, geometry)
}

/** The last moment of a slice: the timeline runs backwards, so this is where the slice begins. */
function endOf(start: string, by: Granularity): string {
  const date = new Date(`${start.slice(0, 10)}T00:00:00Z`)
  if (by === 'year') date.setUTCFullYear(date.getUTCFullYear() + 1)
  if (by === 'month') date.setUTCMonth(date.getUTCMonth() + 1)
  if (by === 'day') date.setUTCDate(date.getUTCDate() + 1)
  date.setUTCSeconds(-1)
  return date.toISOString()
}
