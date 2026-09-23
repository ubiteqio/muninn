import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useScrollContainer } from '@/components/layout/scroll-container'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { useSocialUpdates } from '@/features/social/use-social'
import { DateScrubber } from '@/features/timeline/date-scrubber'
import { DayLoading } from '@/features/timeline/timeline-loading'
import { TimelineTile } from '@/features/timeline/timeline-tile'
import {
  type Geometry,
  groupBy,
  heightAbove,
  heightBelow,
  heightOfAll,
  momentAt,
  scrollPageTo,
  type TimelineShape,
  useTimelineShape,
  useTimelineWindow,
} from '@/features/timeline/use-timeline'
import { useMeasuredWidth } from '@/hooks/use-measured-width'
import { DESKTOP_QUERY, useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'

/** The photo grid of the design: 2 px between tiles. */
const GAP = 2
/** What a day heading takes, heading plus its margin. */
const HEADING = 28
/** How close to the edge of the loaded window the next page is fetched. */
const NEAR_EDGE = 500
/** Days drawn empty while the pictures of the window are on their way. */
const PREVIEW_DAYS = 3

interface TimelineRunProps {
  /** Three columns on mobile, eight on the desktop. */
  columns: number
  /** The month being looked at, as "2014-08". */
  month: string
  /** The medium shown full screen, as it stands in the address. */
  medium: string | undefined
  /** Put another medium into the address, or take it out when the viewer closes. */
  onMediumChange: (mediaId: string | undefined) => void
}

/**
 * One month, day by day.
 *
 * The month is the unit one chose, so the month is what this shows: scrolling to its end does
 * not spill into the year before it. Inside, only a window of three pages is ever in the
 * document, with placeholders above and below standing in for the days that are not loaded - a
 * wedding with two thousand photos scrolls as smoothly as a quiet Tuesday.
 */
export function TimelineRun({ columns, month, medium, onMediumChange }: TimelineRunProps) {
  const { t } = useTranslation()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const container = useScrollContainer()

  // The days of the year, cut down to this month: the placeholders count headings the same way
  // the grid draws them, or the page would be the wrong height.
  const year = Number(month.slice(0, 4))
  const shape = useTimelineShape('day', Number.isNaN(year) ? undefined : year)
  const marks = useMemo(() => (shape.data ? daysOf(shape.data, month) : undefined), [shape, month])

  const [anchor, setAnchor] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const timeline = useTimelineWindow(month, anchor)

  const block = useRef<HTMLDivElement>(null)
  const loaded = useRef<HTMLDivElement>(null)
  const width = useMeasuredWidth(block)

  const media = useMemo(
    () => timeline.data?.pages.flatMap((page) => page.items) ?? [],
    [timeline.data],
  )
  const groups = useMemo(() => groupBy(media, 'day', t('timeline.undated')), [media, t])
  const viewer = useMediaViewer(media, {
    current: medium,
    onCurrentChange: onMediumChange,
    social: true,
  })
  useSocialUpdates()

  // Every group knows where its first tile sits in the window, so a click can name a position
  // in the whole month rather than one inside its day.
  const positioned = useMemo(
    () =>
      groups.map((group, index) => ({
        group,
        start: groups.slice(0, index).reduce((count, earlier) => count + earlier.media.length, 0),
      })),
    [groups],
  )

  const tile = width > 0 ? (width - GAP * (columns - 1)) / columns : 0
  const geometry: Geometry = { columns, rowHeight: tile + GAP, heading: HEADING }

  // The days the window is about to show: the top of the month, or wherever the rail has
  // carried it. Drawn empty, they give the run its height before the first picture is here.
  const preview = useMemo(() => {
    if (!timeline.isPending || !marks) return []
    const day = anchor?.slice(0, 10)
    const from =
      day === undefined ? 0 : Math.max(marks.marks.findIndex((mark) => mark.start <= day), 0)
    return marks.marks.slice(from, from + PREVIEW_DAYS)
  }, [anchor, marks, timeline.isPending])

  const first = groups[0]?.id ?? null
  const last = groups.at(-1)?.id ?? null
  // Loaded or still coming, the spacers hang on the same two days, so the month is its full
  // length either way and nothing moves when the pictures arrive.
  const firstKey = first !== null && first !== 'undated' ? first : (preview[0]?.start ?? null)
  const lastKey = last !== null && last !== 'undated' ? last : (preview.at(-1)?.start ?? null)
  const above = marks && firstKey !== null ? heightAbove(marks, firstKey, geometry) : 0
  const below = marks && lastKey !== null ? heightBelow(marks, lastKey, geometry) : 0
  const total = marks ? heightOfAll(marks, geometry) : 0

  /** Where the timeline block begins inside the scrolling page. */
  const blockTop = useCallback(() => {
    const element = block.current
    if (!element || !container) return 0
    return (
      element.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop
    )
  }, [container])

  // Where the viewer stands inside the month, and what to do about it: fetch the next page, the
  // one before it, or - when the viewport has landed in a placeholder - move the whole window.
  const follow = useCallback(() => {
    const element = block.current
    const window = loaded.current
    if (!element || !window || !container || !marks || total === 0) return

    const offset = container.getBoundingClientRect().top - element.getBoundingClientRect().top
    const viewport = container.clientHeight
    const windowBottom = above + window.offsetHeight

    setProgress(Math.min(Math.max(offset / total, 0), 1))

    if (offset + viewport < above - NEAR_EDGE || offset > windowBottom + NEAR_EDGE) {
      const moment = momentAt(marks, offset / total)
      if (moment !== null && moment !== anchor) setAnchor(moment)
      return
    }

    if (timeline.isFetching) return
    if (offset + viewport > windowBottom - NEAR_EDGE && timeline.hasNextPage) {
      void timeline.fetchNextPage()
    } else if (offset < above + NEAR_EDGE && timeline.hasPreviousPage) {
      void timeline.fetchPreviousPage()
    }
  }, [above, anchor, container, marks, timeline, total])

  useEffect(() => {
    if (!container) return

    let frame = 0
    const onScroll = () => {
      if (frame === 0) {
        frame = requestAnimationFrame(() => {
          frame = 0
          follow()
        })
      }
    }

    onScroll()
    container.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      container.removeEventListener('scroll', onScroll)
      if (frame !== 0) cancelAnimationFrame(frame)
    }
  }, [container, follow])

  /** Dragged on the rail: scroll there, the rest follows from the scroll position. */
  const seek = useCallback(
    (share: number) => {
      if (!container || total === 0) return
      scrollPageTo(container, blockTop() + share * total)
    },
    [blockTop, container, total],
  )

  if (marks && marks.total === 0) {
    return <p className="mt-3 text-base text-muted-foreground">{t('timeline.emptyMonth')}</p>
  }

  return (
    <>
      <div className="mt-3 flex gap-0">
        <div ref={block} className="min-w-0 flex-1" aria-busy={timeline.isPending || undefined}>
          {timeline.isPending && <span className="sr-only">{t('common.loading')}</span>}
          <div aria-hidden="true" style={{ height: above }} />

          <div ref={loaded} className="space-y-4">
            {preview.map((mark) => (
              <DayLoading key={mark.start} columns={columns} count={mark.count} />
            ))}
            {positioned.map(({ group, start }) => (
              <div key={group.id}>
                <h3 className="mb-1.5 text-sm-plus font-semibold text-foreground">
                  {group.label}
                  {group.estimated && (
                    // Every date of this day was guessed. Said here, not on the pictures.
                    <span
                      className="ml-1.5 font-normal text-muted-foreground"
                      title={t('media.estimated')}
                    >
                      ≈
                    </span>
                  )}
                </h3>
                <div
                  className="grid gap-0.5"
                  style={{ gridTemplateColumns: `repeat(${String(columns)}, minmax(0, 1fr))` }}
                >
                  {group.media.map((item, index) => (
                    <TimelineTile
                      key={item.id}
                      medium={item}
                      onOpen={() => {
                        viewer.open(start + index)
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div aria-hidden="true" style={{ height: below }} />
        </div>

        {/* Reserved column so that the handle never sits on a photo. */}
        <DateScrubber
          progress={progress}
          onSeek={seek}
          handleHeight={isDesktop ? 32 : 30}
          className={cn('shrink-0 self-stretch', isDesktop && 'ml-3')}
        />
      </div>

      {viewer.panel}
    </>
  )
}

/** The days of one month, out of the days of its year. */
function daysOf(shape: TimelineShape, month: string): TimelineShape {
  const marks = shape.marks.filter((mark) => mark.start.slice(0, 7) === month)
  return { by: 'day', total: marks.reduce((all, mark) => all + mark.count, 0), marks }
}
