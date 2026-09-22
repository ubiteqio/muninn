import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface SectionHeadingProps {
  title: string
  /** Right hand side: "Alle ansehen", the link to all albums or the live date chip. */
  action?: ReactNode
  className?: string | undefined
  /** For the section's aria-labelledby: the heading names the section for a screen reader. */
  id?: string | undefined
}

export function SectionHeading({ title, action, className, id }: SectionHeadingProps) {
  return (
    <div className={cn('flex items-center justify-between gap-3', className)}>
      <h2
        id={id}
        className="text-xs font-semibold uppercase tracking-section text-muted-foreground"
      >
        {title}
      </h2>
      {action}
    </div>
  )
}
