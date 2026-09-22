import { cn } from '@/lib/utils'

/**
 * Two crossed hatchings at 10 % opacity, the Norse knotwork of the design. It separates sections
 * and must never sit on top of a photo.
 */
export function Knotwork({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('knotwork w-full', className)} />
}
