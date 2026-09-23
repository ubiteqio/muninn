import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { useScrollContainer } from '@/components/layout/scroll-container'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useLibraryUpdates } from '@/features/albums/use-library-updates'
import { RunLoading } from '@/features/timeline/timeline-loading'
import { TimelineOverview } from '@/features/timeline/timeline-overview'
import { TimelineRun } from '@/features/timeline/timeline-run'
import {
  labelOf,
  type Level,
  scrollPageTo,
  useTimelineShape,
} from '@/features/timeline/use-timeline'

interface TimelineSectionProps {
  /** Three columns on mobile, eight on the desktop. */
  columns: number
  /** How far away the library is looked at, from the address. */
  level: Level
  /** Which year or month is being looked at: "2014" or "2014-08". */
  at: string | undefined
  /** Move to another level, at another period. */
  onLevelChange: (level: Level, at: string | undefined) => void
  /** The medium shown full screen, as it stands in the address. */
  medium: string | undefined
  onMediumChange: (mediaId: string | undefined) => void
  className?: string
}

/**
 * The timeline at three distances: the years, the months of a year, and the run itself.
 *
 * Which one is open stands in the address, so a year can be sent to somebody and the back button
 * steps out one level rather than leaving the page. Each level answers the question the one
 * above it raises: which year, which month, and then the pictures themselves.
 */
export function TimelineSection({
  columns,
  level,
  at,
  onLevelChange,
  medium,
  onMediumChange,
  className,
}: TimelineSectionProps) {
  const { t } = useTranslation()
  const container = useScrollContainer()
  const shape = useTimelineShape()
  const section = useRef<HTMLElement>(null)
  // Whether the section has already scrolled once: stepping between levels moves the page,
  // arriving on it must not.
  const stepped = useRef(false)
  useLibraryUpdates()

  // Stepping between levels means a page of a completely different height. Without this one
  // lands wherever the old page happened to be scrolled to - halfway down a year, usually.
  useEffect(() => {
    const element = section.current
    if (!element || !container) return

    // On the way in the page already stands at its top, and on a phone the start screen has
    // four sections above this one that one is meant to see first. Now that they hold their
    // height from the first frame, jumping to the timeline would scroll straight past them.
    if (!stepped.current) {
      stepped.current = true
      return
    }

    const top =
      element.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop
    scrollPageTo(container, Math.max(top - 16, 0))
  }, [at, container, level])

  const marks = shape.data
  const summary =
    marks && marks.total > 0
      ? t('timeline.summary', {
          count: marks.total,
          from: marks.marks.at(-1)?.start.slice(0, 4) ?? '',
          to: marks.marks[0]?.start.slice(0, 4) ?? '',
        })
      : ''

  // The run always shows one month. Without one in the address - a bare link, or a browser that
  // kept the level but not the place - the newest month the library has is the sensible one.
  const months = marks?.marks.map((mark) => mark.start.slice(0, 7)) ?? []
  const month = at?.length === 7 && months.includes(at) ? at : months[0]
  const standingAt = months.indexOf(month ?? '')
  const older = standingAt >= 0 ? months[standingAt + 1] : undefined
  const newer = standingAt > 0 ? months[standingAt - 1] : undefined

  // How many cards the level will show. The shape names every month the library holds, so the
  // placeholders can stand at the height the cards will take instead of at a round number.
  const year = at?.slice(0, 4)
  const cards =
    marks === undefined
      ? 0
      : level === 'years'
        ? new Set(marks.marks.map((mark) => mark.start.slice(0, 4))).size
        : marks.marks.filter((mark) => year === undefined || mark.start.startsWith(year)).length
  const up =
    level === 'days'
      ? { level: 'months' as const, at: year, label: year ?? t('timeline.years') }
      : level === 'months'
        ? { level: 'years' as const, at: undefined, label: t('timeline.years') }
        : null

  return (
    <section ref={section} aria-labelledby="timeline-heading" className={className}>
      <SectionHeading
        id="timeline-heading"
        title={t('timeline.title')}
        action={
          // A fixed lane: the chip and the way back come and go with the level, and without a
          // height of its own the heading would grow and shrink with them - and every picture
          // below it would move.
          <div className="flex h-9 items-center gap-3">
            {summary && (
              <span className="hidden text-sm text-muted-foreground lg:inline">{summary}</span>
            )}
            {level === 'days' && month && (
              <Badge variant="amber" className="font-bold">
                {shortLabel(labelOf(month))}
              </Badge>
            )}
            {up && (
              <Button
                variant="outline"
                className="h-8 px-2 text-xs-plus"
                onClick={() => {
                  onLevelChange(up.level, up.at)
                }}
              >
                <Symbol name="arrow_back" size={16} />
                {up.label}
              </Button>
            )}
          </div>
        }
      />

      {marks?.total === 0 && (
        <p className="mt-3 text-base text-muted-foreground">{t('timeline.empty')}</p>
      )}

      {level === 'years' && marks?.total !== 0 && (
        <TimelineOverview
          by="year"
          count={cards}
          onOpen={(period) => {
            onLevelChange('months', period)
          }}
        />
      )}

      {level === 'months' && marks?.total !== 0 && (
        <TimelineOverview
          by="month"
          year={year === undefined ? undefined : Number(year)}
          count={cards}
          onOpen={(period) => {
            onLevelChange('days', period)
          }}
        />
      )}

      {/* No month yet, so not even the run can be mounted: it would not know what to ask for. */}
      {level === 'days' && month === undefined && shape.isPending && (
        <RunLoading columns={columns} />
      )}

      {level === 'days' && month && (
        <>
          <TimelineRun
            // Another month is another run, not the same one moved.
            key={month}
            columns={columns}
            month={month}
            medium={medium}
            onMediumChange={onMediumChange}
          />

          {/* The months around this one, in the order a timeline runs: earlier on the left. */}
          <nav aria-label={t('timeline.months')} className="mt-4 flex items-center gap-3">
            {older && (
              <Button
                variant="outline"
                onClick={() => {
                  onLevelChange('days', older)
                }}
              >
                <Symbol name="chevron_left" size={18} />
                {labelOf(older)}
              </Button>
            )}
            {newer && (
              <Button
                variant="outline"
                className="ml-auto"
                onClick={() => {
                  onLevelChange('days', newer)
                }}
              >
                {labelOf(newer)}
                <Symbol name="chevron_right" size={18} />
              </Button>
            )}
          </nav>
        </>
      )}
    </section>
  )
}

/** The chip shows the month short: "September 2026" -> "Sept. 2026". */
function shortLabel(label: string): string {
  const [month = '', year = ''] = label.split(' ')
  return `${month.length > 5 ? `${month.slice(0, 4)}.` : month} ${year}`
}
