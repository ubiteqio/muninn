import { useTranslation } from 'react-i18next'

import { PeriodCard } from '@/features/timeline/period-card'
import { labelOf, usePeriods } from '@/features/timeline/use-timeline'

interface TimelineOverviewProps {
  /** Every year of the library, or every month of one year. */
  by: 'year' | 'month'
  /** The year whose months are shown. Ignored when the years themselves are. */
  year?: number | undefined
  /** A card was chosen: "2014" on the years, "2014-08" on the months. */
  onOpen: (period: string) => void
}

/**
 * The library from further away: a card per year, or per month of one year.
 *
 * This is what makes twenty-six years walkable. A month of eight hundred photos is forty screens
 * of scrolling; as a card it is one square that says how much is in it and what it looked like.
 */
export function TimelineOverview({ by, year, onOpen }: TimelineOverviewProps) {
  const { t } = useTranslation()
  const periods = usePeriods(by, year)

  if (periods.data?.length === 0) {
    return <p className="mt-3 text-base text-muted-foreground">{t('timeline.empty')}</p>
  }

  if (periods.isPending) {
    // Squares of the right size rather than a line of text: the page keeps its height, and
    // nothing below the timeline moves when the cards arrive.
    return (
      <div
        aria-label={t('timeline.loading')}
        aria-busy="true"
        className="mt-3 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
      >
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="aspect-square w-full rounded-lg bg-secondary/40" />
        ))}
      </div>
    )
  }

  return (
    <div className="mt-3 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
      {periods.data?.map((period) => (
        <PeriodCard
          key={period.start}
          period={period}
          label={by === 'year' ? period.start.slice(0, 4) : labelOf(period.start.slice(0, 7))}
          onOpen={() => {
            onOpen(period.start.slice(0, by === 'year' ? 4 : 7))
          }}
        />
      ))}
    </div>
  )
}
