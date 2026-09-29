import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

/**
 * The long answer to "what does this do", one tap away.
 *
 * Settings carry a line under them saying what the number means and where its bounds are. That
 * line has to stay short, and short is not enough for a value one meets twice a year: what it
 * changes, what happens to what is already there, and which value is a sensible one. That
 * belongs here rather than in the line, which would otherwise grow into a paragraph on every
 * field.
 *
 * It opens on a click, never on hovering: half of Muninn is read on a phone, where there is no
 * such thing.
 */
export function InfoHint({ about, children }: { about: string; children: React.ReactNode }) {
  const { t } = useTranslation()

  return (
    <Popover>
      <PopoverTrigger
        type="button"
        aria-label={t('common.explain', { name: about })}
        className="-m-1 flex size-7 shrink-0 items-center justify-center rounded-full p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[state=open]:bg-secondary data-[state=open]:text-foreground"
      >
        <Symbol name="info" size={17} />
      </PopoverTrigger>
      <PopoverContent>
        <p className="text-sm font-medium text-foreground">{about}</p>
        <div className="mt-1.5 space-y-2 text-xs-plus text-muted-foreground">{children}</div>
      </PopoverContent>
    </Popover>
  )
}
