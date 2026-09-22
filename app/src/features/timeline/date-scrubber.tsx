import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

interface DateScrubberProps {
  /** How far through the timeline the viewer stands, between 0 (today) and 1 (the oldest). */
  progress: number
  /** Dragged to a new position on the rail. */
  onSeek: (progress: number) => void
  /** 30 px on mobile, 32 px on the desktop. */
  handleHeight?: number
  className?: string
}

/**
 * The rail on the right edge of the timeline.
 *
 * It stands for the whole library, not for the part that happens to be loaded: dragging the
 * handle carries the window to that point. Where one lands is said by the chip in the heading
 * and by the day headings themselves - the rail carries no years of its own, because years fall
 * on top of each other wherever the library is uneven, which is everywhere.
 *
 * It lives in its own reserved column: the grid keeps a padding to the right so that the handle
 * never sits on a photo.
 */
export function DateScrubber({
  progress,
  onSeek,
  handleHeight = 30,
  className,
}: DateScrubberProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)

  const seekToPointer = useCallback(
    (clientY: number) => {
      const track = trackRef.current
      if (!track) return

      const bounds = track.getBoundingClientRect()
      onSeek(Math.min(Math.max((clientY - bounds.top) / bounds.height, 0), 1))
    },
    [onSeek],
  )

  useEffect(() => {
    if (!dragging) return

    const onMove = (event: PointerEvent) => {
      event.preventDefault()
      seekToPointer(event.clientY)
    }
    const onUp = () => {
      setDragging(false)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [dragging, seekToPointer])

  return (
    <div
      ref={trackRef}
      className={cn('relative w-4 py-1', className)}
      onPointerDown={(event) => {
        setDragging(true)
        seekToPointer(event.clientY)
      }}
    >
      <ScrubberHandle progress={progress} height={handleHeight} />
    </div>
  )
}

function ScrubberHandle({ progress, height }: { progress: number; height: number }) {
  const { t } = useTranslation()

  return (
    <span
      role="presentation"
      aria-label={t('timeline.scrubber')}
      className="pointer-events-none absolute right-0 w-1.5 rounded-[3px] bg-accent shadow-handle"
      style={{
        height,
        top: `calc(${String(progress * 100)}% - ${String(progress * height)}px)`,
      }}
    />
  )
}
