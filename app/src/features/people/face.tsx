import { cn } from '@/lib/utils'

/** The square picture of a face, cut on the server from the frame it was found in. */
export function Face({
  src,
  size,
  className,
}: {
  src: string | null | undefined
  size: number
  className?: string
}) {
  return (
    <span
      className={cn('block shrink-0 overflow-hidden rounded-full bg-secondary', className)}
      style={{ width: size, height: size }}
    >
      {src && <img src={src} alt="" loading="lazy" className="size-full object-cover" />}
    </span>
  )
}
