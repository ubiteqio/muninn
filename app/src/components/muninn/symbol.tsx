import { cn } from '@/lib/utils'

interface SymbolProps {
  /** Material Symbols Rounded ligature name, e.g. "home" or "chat_bubble". */
  name: string
  /** Filled shape. The design uses it for the active navigation target only. */
  filled?: boolean
  size?: number
  weight?: number
  className?: string
}

/**
 * An icon from Material Symbols Rounded. Icons are decoration next to their label, so they are
 * hidden from screen readers; anything that stands alone carries its own aria-label.
 */
export function Symbol({ name, filled = false, size = 24, weight = 400, className }: SymbolProps) {
  return (
    <span
      aria-hidden="true"
      className={cn('symbol', filled && 'symbol-filled', className)}
      style={{
        fontSize: `${String(size)}px`,
        width: `${String(size)}px`,
        height: `${String(size)}px`,
        ['--symbol-weight' as string]: weight,
      }}
    >
      {name}
    </span>
  )
}
