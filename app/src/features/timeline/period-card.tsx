import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import type { Period } from '@/features/timeline/use-timeline'
import { cn } from '@/lib/utils'

/**
 * One year or one month, as a mosaic of what is in it.
 *
 * Four pictures rather than one: a single cover says what the newest picture was, four say what
 * the period felt like. Fewer than four fill the square between them, so the card is never a
 * grid with holes in it.
 */
export function PeriodCard({
  period,
  label,
  onOpen,
  className,
}: {
  period: Period
  label: string
  onOpen: () => void
  className?: string
}) {
  const { t } = useTranslation()
  const covers = period.covers.slice(0, 4)

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t('timeline.openPeriod', { period: label, count: period.count })}
      className={cn('group block w-full text-left', className)}
    >
      <div
        className={cn(
          'grid aspect-square w-full gap-0.5 overflow-hidden rounded-lg bg-secondary/60 transition group-hover:ring-1 group-hover:ring-primary/35',
          covers.length > 1 && 'grid-cols-2',
          // Named, not left to the pictures. Without this the square is divided by what landed
          // in it - each row as tall as its photograph - and the mosaic comes out lopsided.
          covers.length > 2 && 'grid-rows-2',
        )}
      >
        {covers.length === 0 ? (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            <Symbol name="history" size={22} />
          </span>
        ) : (
          covers.map((cover, index) => (
            <img
              key={cover.id}
              src={cover.thumb}
              alt=""
              loading="lazy"
              decoding="async"
              className={cn(
                'h-full min-h-0 w-full min-w-0 object-cover',
                // Three pictures: the first one takes the whole left half.
                covers.length === 3 && index === 0 && 'row-span-2',
              )}
            />
          ))
        )}
      </div>

      <p className="mt-2 truncate text-base font-semibold text-foreground">{label}</p>
      <p className="truncate text-xs-plus text-muted-foreground">
        {t('timeline.periodCount', { count: period.count })}
      </p>
    </button>
  )
}
