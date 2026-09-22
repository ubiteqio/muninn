import { cva, type VariantProps } from 'class-variance-authority'
import type * as React from 'react'

import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1 font-semibold', {
  variants: {
    variant: {
      /** Amber pill, e.g. the live date chip in the timeline heading. */
      amber: 'rounded-full bg-primary/[0.16] px-2 py-1 text-xs text-accent',
      /**
       * Glass chip over a photo, e.g. "Heute vor 5 Jahren". Dark in both looks: it sits on the
       * picture, not on the page, and a light chip on a bright photo cannot be read.
       */
      glass:
        'rounded-full border border-[rgba(227,167,59,0.4)] bg-[rgba(11,13,18,0.62)] px-2.5 py-1 text-xs font-semibold text-[#F4C878] backdrop-blur-chip',
      /** Count chip in the corner of an album cover. */
      count: 'rounded-chip bg-background/[0.66] px-1.5 py-0.5 text-2xs text-foreground',
      /** Video duration and similar overlays. */
      overlay: 'rounded-badge bg-background/60 px-1 py-0.5 text-3xs text-foreground',
    },
  },
  defaultVariants: {
    variant: 'amber',
  },
})

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
