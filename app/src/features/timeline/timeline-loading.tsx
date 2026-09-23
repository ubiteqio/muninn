import { useTranslation } from 'react-i18next'

import { Placeholder } from '@/components/muninn/placeholder'

/** Cards for a library that has not said yet how many years it holds. */
const WAITING_CARDS = 12

/** Days of three rows each, for a month whose days are not known yet. */
const WAITING_DAYS = 3
const WAITING_ROWS = 3

/**
 * The cards of a level while they are on their way: the square the mosaic will fill and the two
 * lines under it.
 *
 * How many of them is not a guess. The shape of the timeline names every month the library
 * holds, so the years - and the months of one year - can be counted before a single card is
 * here. Six squares for twenty-six years would leave the page four rows short on the desktop.
 */
export function OverviewLoading({ count }: { count: number }) {
  const { t } = useTranslation()

  return (
    <>
      <span className="sr-only">{t('common.loading')}</span>
      <div
        aria-busy="true"
        className="mt-3 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
      >
        {Array.from({ length: count > 0 ? count : WAITING_CARDS }, (_, index) => (
          <div key={index}>
            <Placeholder className="aspect-square w-full rounded-lg" />
            {/* The label and the count under the square take 42 px together, and so do these. */}
            <Placeholder className="mt-2 h-4 w-16" />
            <Placeholder className="mt-1.5 h-3 w-20" />
          </div>
        ))}
      </div>
    </>
  )
}

/**
 * One day of the run, as empty tiles in the grid its pictures will fill.
 *
 * The heading stays a block rather than the date it will carry: whether a day's dates were
 * guessed is only known once its media are here, and a heading that gains a "≈" afterwards is
 * a heading that changed under the reader.
 */
export function DayLoading({ columns, count }: { columns: number; count: number }) {
  return (
    <div>
      {/* The lane a day heading takes, heading and margin together. */}
      <div className="mb-1.5 flex h-[17.5px] items-center">
        <Placeholder className="h-3 w-40" />
      </div>
      <div
        className="grid gap-0.5"
        style={{ gridTemplateColumns: `repeat(${String(columns)}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: count }, (_, index) => (
          <Placeholder key={index} className="aspect-square w-full rounded-none" />
        ))}
      </div>
    </div>
  )
}

/**
 * The run before the library has said which months it has.
 *
 * Three days of three rows is the one guess on this screen: the moment the shape answers, every
 * height comes from the day counts themselves. The rail keeps its column throughout, so the
 * tiles are not a hair wider now than they will be.
 */
export function RunLoading({ columns }: { columns: number }) {
  const { t } = useTranslation()

  return (
    <>
      <span className="sr-only">{t('common.loading')}</span>
      <div aria-busy="true" className="mt-3 flex gap-0">
        <div className="min-w-0 flex-1 space-y-4">
          {Array.from({ length: WAITING_DAYS }, (_, index) => (
            <DayLoading key={index} columns={columns} count={WAITING_ROWS * columns} />
          ))}
        </div>
        {/* The reserved column of the rail, so the tiles are not wider now than later. */}
        <div aria-hidden="true" className="w-4 shrink-0 lg:ml-3" />
      </div>
    </>
  )
}
