import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * A quiet block that stands where something is still being fetched, in the shape it will have.
 * The page then keeps its layout instead of pushing content around as the answers arrive.
 * A sheen travels over it, so it reads as "on its way" rather than as empty furniture.
 */
export function Placeholder({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn('placeholder rounded-md bg-secondary/70', className)} />
  )
}

/**
 * The box the placeholders stand in: the outline of the section that is coming, so the page
 * already has its shape while the answers are on their way.
 */
export function PlaceholderBox({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-hairline/10 bg-card/60 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.03)]',
        className,
      )}
    >
      {children}
    </div>
  )
}
