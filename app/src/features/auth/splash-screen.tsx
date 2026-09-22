import { useTranslation } from 'react-i18next'

import { Wordmark } from '@/components/layout/logo'
import { cn } from '@/lib/utils'

const MARK = 134

/**
 * The mark large in the middle of the page with the name under it. The raven is dark navy, so
 * it sits on its parchment tile in both themes; a long soft shadow lifts the tile off the page.
 * Shared by the wait while the session is restored and the intro, so one runs into the other
 * without the logo jumping.
 */
export function BrandSplash({ pulsing = false }: { pulsing?: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 bg-background">
      <span
        className={cn(
          'flex items-center justify-center border border-[#EDE6D6]/50 bg-[#EDE6D6] shadow-[0_24px_60px_-24px_rgba(11,13,18,0.5)]',
          pulsing && 'animate-pulse motion-reduce:animate-none',
        )}
        style={{ width: MARK, height: MARK, borderRadius: 38 }}
      >
        <img
          src="/muninn-mark.png"
          alt=""
          aria-hidden="true"
          className="object-contain"
          style={{ width: MARK * 0.82, height: MARK * 0.82 }}
        />
      </span>
      <Wordmark className="text-[30px]" />
    </div>
  )
}

/**
 * Shown while the session is being restored. The design asks for two ravens circling each other as
 * the app-wide loading animation; until that artwork exists this is the quiet version of it: the
 * mark on its parchment tile, breathing.
 */
export function SplashScreen() {
  const { t } = useTranslation()

  return (
    <div role="status" aria-label={t('auth.loading')} className="h-full">
      <BrandSplash pulsing />
    </div>
  )
}
