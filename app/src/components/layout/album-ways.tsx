import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ALBUM_WAYS } from '@/components/layout/navigation'
import { Symbol } from '@/components/muninn/symbol'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

/**
 * "Alben" leads to two places now: the folders of the NAS, and the Smarts that sort the same
 * media by what is in them. Rather than spending a second seat in a rail of five, the
 * destination opens a small menu - the same one in the rail and in the phone's bottom bar, so
 * the two ways are found in the same gesture wherever somebody is.
 */
export function AlbumWays({
  trigger,
  side = 'right',
  align = 'start',
}: {
  trigger: ReactNode
  side?: 'right' | 'top'
  align?: 'start' | 'center'
}) {
  const { t } = useTranslation()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent side={side} align={align} className="min-w-[190px]">
        {ALBUM_WAYS.map((way) => (
          <DropdownMenuItem key={way.id} asChild>
            <Link to={way.to} className="flex items-start gap-2.5">
              <Symbol name={way.icon} size={20} className="mt-0.5 shrink-0" />
              <span className="flex flex-col">
                <span className="font-medium">{t(`nav.way.${way.id}`)}</span>
                <span className={cn('text-2xs text-muted-foreground')}>
                  {t(`nav.wayHint.${way.id}`)}
                </span>
              </span>
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
