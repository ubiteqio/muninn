import type { CSSProperties } from 'react'

import { initialsOf } from '@/features/auth/initials'
import { cn } from '@/lib/utils'

/** The same name always gets the same hue, so a person keeps their colour everywhere. */
function hueOf(name: string): number {
  return Array.from(name).reduce((sum, letter) => sum + (letter.codePointAt(0) ?? 0), 0) % 360
}

/**
 * A person as their initials on a quiet tint of their own - own avatar, comments and news alike.
 *
 * Flat and low in saturation, so it sits on parchment and on Rabenschwarz without shouting, and
 * never reads as the amber of a button. The colours themselves live in `.person-initial`, which
 * knows both themes.
 */
export function PersonInitial({
  name,
  size,
  className,
}: {
  name: string
  size: number
  className?: string | undefined
}) {
  const style = {
    width: size,
    height: size,
    fontSize: Math.round(size * 0.4),
    '--person-hue': String(hueOf(name)),
  } as CSSProperties

  return (
    <span
      aria-hidden="true"
      className={cn(
        'person-initial flex shrink-0 select-none items-center justify-center rounded-full font-semibold',
        className,
      )}
      style={style}
    >
      {initialsOf(name)}
    </span>
  )
}
