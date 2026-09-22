import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

/**
 * From here on the server assigns a face without asking - measured against faces somebody
 * confirmed. A suggestion measured against one Muninn gave may lie above.
 */
const AUTO_FROM = 0.55
/** From here on a suggestion shows green: a yes is likely. */
const LIKELY_FROM = 0.45

/**
 * "Ähnlichkeit 47 %": how alike the face is to the nearest face of the suggested person. Green
 * from 45 % on - a hint where a yes is likely.
 */
export function Similarity({
  value,
  className,
}: {
  value: number | null | undefined
  className?: string
}) {
  const { t } = useTranslation()
  if (value === null || value === undefined) return null
  const percent = Math.round(value * 100)
  const close = value >= LIKELY_FROM
  return (
    <span
      title={t('people.similarityHint', { auto: Math.round(AUTO_FROM * 100) })}
      className={cn(
        'rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums',
        close
          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
          : 'bg-secondary text-muted-foreground',
        className,
      )}
    >
      {t('people.similarity', { percent })}
    </span>
  )
}
