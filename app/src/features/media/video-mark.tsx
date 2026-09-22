import { Symbol } from '@/components/muninn/symbol'
import { formatDuration } from '@/features/media/format'
import { cn } from '@/lib/utils'

/**
 * What makes a video tile a video at a glance: a play button in the middle, and its length on a
 * soft shade at the bottom. The same in albums, timeline and search. Drawn over the picture and
 * never in the way of a click - the tile underneath is the button.
 */
export function VideoMark({
  seconds,
  compact = false,
}: {
  seconds: number | null | undefined
  /** The small tiles of the timeline: a smaller button, the same length. */
  compact?: boolean
}) {
  const length = formatDuration(seconds ?? null)

  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0">
      <span className="absolute inset-0 flex items-center justify-center">
        <span
          className={cn(
            'flex items-center justify-center rounded-full bg-black/45 text-white ring-1 ring-white/25 backdrop-blur-[2px]',
            compact ? 'h-7 w-7' : 'h-9 w-9 sm:h-11 sm:w-11',
          )}
        >
          <Symbol name="play_arrow" size={compact ? 18 : 24} filled />
        </span>
      </span>
      {length && (
        <>
          <span className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/55 to-transparent" />
          <span
            className={cn(
              'absolute bottom-1 right-1.5 font-medium tabular-nums text-white drop-shadow',
              compact ? 'text-2xs' : 'text-xs',
            )}
          >
            {length}
          </span>
        </>
      )}
    </span>
  )
}
