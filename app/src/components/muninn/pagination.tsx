import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { pagesAround } from '@/lib/pages'
import { cn } from '@/lib/utils'

const ROUND =
  'grid size-9 shrink-0 place-items-center rounded-full text-base tabular-nums transition disabled:pointer-events-none disabled:opacity-35'

/**
 * Page numbers with arrows. On a phone the numbers give way to "2 / 3", which fits beside the
 * arrows at any width; from sm on every page near the current one is a tap away.
 */
export function Pagination({
  page,
  pages,
  onPage,
  className,
}: {
  page: number
  pages: number
  onPage: (page: number) => void
  className?: string
}) {
  const { t } = useTranslation()
  if (pages <= 1) return null

  return (
    <nav aria-label={t('pagination.label')} className={cn('flex items-center gap-1', className)}>
      <button
        type="button"
        aria-label={t('pagination.previous')}
        disabled={page <= 1}
        className={cn(ROUND, 'text-foreground hover:bg-secondary')}
        onClick={() => {
          onPage(page - 1)
        }}
      >
        <Symbol name="chevron_left" size={22} />
      </button>

      <span className="min-w-14 text-center text-base tabular-nums text-muted-foreground sm:hidden">
        {t('pagination.of', { page, pages })}
      </span>

      <ul className="hidden items-center gap-1 sm:flex">
        {pagesAround(page, pages).map((item, index) =>
          item === 'gap' ? (
            <li
              key={`gap-${String(index)}`}
              aria-hidden="true"
              className="w-6 text-center text-muted-foreground"
            >
              …
            </li>
          ) : (
            <li key={item}>
              <button
                type="button"
                aria-label={t('pagination.page', { page: item })}
                aria-current={item === page ? 'page' : undefined}
                className={cn(
                  ROUND,
                  item === page
                    ? 'bg-primary font-semibold text-primary-foreground'
                    : 'text-foreground hover:bg-secondary',
                )}
                onClick={() => {
                  onPage(item)
                }}
              >
                {item}
              </button>
            </li>
          ),
        )}
      </ul>

      <button
        type="button"
        aria-label={t('pagination.next')}
        disabled={page >= pages}
        className={cn(ROUND, 'text-foreground hover:bg-secondary')}
        onClick={() => {
          onPage(page + 1)
        }}
      >
        <Symbol name="chevron_right" size={22} />
      </button>
    </nav>
  )
}
