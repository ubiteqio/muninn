import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'

/**
 * A panel of the viewer: on the phone a sheet from below, from the tablet upwards a column beside
 * the picture. Details and comments both open in it, one at a time. It carries data-viewer-panel,
 * so a tap on the picture beside it closes it and a tap inside does not.
 */
export function ViewerSheet({
  label,
  title,
  onClose,
  children,
}: {
  label: string
  title: ReactNode
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useTranslation()

  return (
    <aside
      aria-label={label}
      data-viewer-panel=""
      // Above PhotoSwipe's own layers, which end at 1550.
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-[1600] max-h-[70svh] overflow-y-auto rounded-t-xl border-t border-hairline/10 bg-background/95 p-5 pb-[max(env(safe-area-inset-bottom),20px)] backdrop-blur md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-80 md:rounded-none md:border-l md:border-t-0"
    >
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-md font-semibold text-foreground">{title}</h2>
        <Button variant="ghost" size="icon" aria-label={t('common.close')} onClick={onClose}>
          <Symbol name="close" size={20} />
        </Button>
      </header>
      {children}
    </aside>
  )
}
