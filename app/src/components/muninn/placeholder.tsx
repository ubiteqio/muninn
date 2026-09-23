import { cn } from '@/lib/utils'

/**
 * A quiet block that stands where something is still being fetched, in the shape it will have.
 * The page then keeps its layout instead of pushing content around as the answers arrive.
 */
export function Placeholder({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'animate-pulse rounded-md bg-secondary/60 motion-reduce:animate-none',
        className,
      )}
    />
  )
}
