import type { ReactNode } from 'react'

import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

/**
 * What a section says when it has nothing to show yet: one quiet line on a card, the same shape
 * in every section so an empty start screen reads as one page.
 */
export function EmptyNote({
  children,
  className,
}: {
  children: ReactNode
  className?: string | undefined
}) {
  return (
    <Card className={cn('mt-3', className)}>
      <p className="p-4 text-base text-muted-foreground">{children}</p>
    </Card>
  )
}
