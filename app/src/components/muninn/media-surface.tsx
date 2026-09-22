import { cn } from '@/lib/utils'

/**
 * Stands in for a photo or video.
 *
 * Every medium carries a dominant colour; until the real file is loaded the design shows that
 * colour blurred instead of a grey box. Milestone 2 fills `gradient` from the index, so the
 * loading state and the placeholder look the same by construction.
 */
export function MediaSurface({
  gradient,
  loading = false,
  className,
}: {
  gradient: string
  loading?: boolean
  className?: string
}) {
  return (
    <div
      aria-hidden="true"
      className={cn('absolute inset-0', loading && 'blur-[12px]', className)}
      style={{ backgroundImage: gradient }}
    />
  )
}
