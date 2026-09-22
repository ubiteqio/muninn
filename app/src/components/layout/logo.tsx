import { cn } from '@/lib/utils'

/**
 * The raven mark is dark navy, so it always sits on a parchment tile - on Rabenschwarz it would
 * disappear.
 */
export function LogoMark({ size = 38, className }: { size?: number; className?: string }) {
  return (
    <span
      className={cn(
        'flex items-center justify-center rounded-mark border border-[#EDE6D6]/50 bg-[#EDE6D6]',
        className,
      )}
      style={{ width: size, height: size }}
    >
      <img
        src="/muninn-mark.png"
        alt=""
        aria-hidden="true"
        className="object-contain"
        style={{ width: size * 0.82, height: size * 0.82 }}
      />
    </span>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('text-[20px] font-semibold tracking-wordmark text-foreground', className)}>
      MUNINN
    </span>
  )
}
