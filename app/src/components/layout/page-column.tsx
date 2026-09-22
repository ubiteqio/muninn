import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * The column of a page of forms and cards - admin area and profile alike: 680 px, 960 px from
 * 1024 px on, 1200 px on very wide screens. One width, so moving between them nothing jumps.
 */
export function PageColumn({
  children,
  className,
}: {
  children: ReactNode
  className?: string | undefined
}) {
  return (
    <div
      className={cn(
        'mx-auto max-w-[680px] px-5 md:px-0 lg:max-w-[960px] 2xl:max-w-[1200px]',
        className,
      )}
    >
      {children}
    </div>
  )
}
