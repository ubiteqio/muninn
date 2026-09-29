import { useVirtualizer } from '@tanstack/react-virtual'
import { type CSSProperties, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { useScrollContainer } from '@/components/layout/scroll-container'
import { Placeholder } from '@/components/muninn/placeholder'
import { Symbol } from '@/components/muninn/symbol'
import type { Medium } from '@/features/albums/use-albums'
import { formatDate } from '@/features/media/format'
import { VideoMark } from '@/features/media/video-mark'
import { useMeasuredWidth } from '@/hooks/use-measured-width'
import { cn } from '@/lib/utils'

const GAP = 6

/**
 * How much of the grid stands there while the pictures are fetched. A screenful, no more:
 * beyond the fold there is nothing waiting to be pushed down, and a box longer than the album
 * turns out to be would drop the page when the answer is short.
 */
const LOADING_ROWS = 5
const LOADING_ROWS_WIDE = 4

interface MediaGridProps {
  media: Medium[]
  columns: number
  /** A short word on a tile, by medium id - a search says here where in a video it matched. */
  notes?: ReadonlyMap<string, string> | undefined
  onOpen: (index: number) => void
  /** Called when the last rows come into view, to fetch the next page. */
  onEndReached?: () => void
}

/**
 * The grid of an album.
 *
 * Only the visible rows are rendered: 150.000 tiles in the document would make even scrolling
 * expensive. Until the width is measured - the first frame, and anywhere without layout - the
 * grid renders plainly, so nothing depends on a measurement that may never come.
 */
export function MediaGrid({ media, columns, notes, onOpen, onEndReached }: MediaGridProps) {
  const container = useScrollContainer()
  const grid = useRef<HTMLDivElement>(null)
  const width = useMeasuredWidth(grid)

  const rows = Math.ceil(media.length / columns)
  const tile = width > 0 ? (width - GAP * (columns - 1)) / columns : 0
  const virtualised = tile > 0 && container !== null

  const virtualizer = useVirtualizer({
    count: rows,
    getScrollElement: () => container,
    estimateSize: () => tile + GAP,
    overscan: 3,
    enabled: virtualised,
  })

  /*
   * A row's place is worked out once from the size it was estimated at, and kept. Turning a
   * phone changes both the number of columns and the size of a tile, so without this the rows
   * were drawn at their new size and placed at their old one: they slid over each other, the
   * grid ended in the wrong place, and the whole listing came apart. Saying that the estimate
   * has changed makes it work the places out again.
   */
  useEffect(() => {
    virtualizer.measure()
  }, [virtualizer, tile, columns])

  const virtualRows = virtualizer.getVirtualItems()
  const lastVisibleRow = virtualised ? (virtualRows.at(-1)?.index ?? 0) : rows - 1

  useEffect(() => {
    if (onEndReached && rows > 0 && lastVisibleRow >= rows - 2) onEndReached()
  }, [lastVisibleRow, rows, onEndReached])

  if (!virtualised) {
    return (
      <div
        ref={grid}
        className="grid gap-1.5"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {media.map((medium, index) => (
          <MediaTile
            key={medium.id}
            medium={medium}
            note={notes?.get(medium.id)}
            onOpen={() => {
              onOpen(index)
            }}
          />
        ))}
      </div>
    )
  }

  return (
    <div ref={grid} className="relative" style={{ height: virtualizer.getTotalSize() }}>
      {virtualRows.map((row) => (
        <div
          key={row.key}
          className="absolute left-0 top-0 flex w-full gap-1.5"
          style={{ height: tile, transform: `translateY(${row.start}px)` }}
        >
          {media.slice(row.index * columns, row.index * columns + columns).map((medium, offset) => (
            <MediaTile
              key={medium.id}
              medium={medium}
              note={notes?.get(medium.id)}
              style={{ width: tile, height: tile }}
              onOpen={() => {
                onOpen(row.index * columns + offset)
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function MediaTile({
  medium,
  note,
  style,
  onOpen,
}: {
  medium: Medium
  note?: string | undefined
  style?: CSSProperties
  onOpen: () => void
}) {
  const { t } = useTranslation()

  return (
    <button
      type="button"
      onClick={onOpen}
      style={style}
      aria-label={t('media.open', { date: formatDate(medium.taken_at) })}
      className={cn(
        'group relative aspect-square overflow-hidden rounded-md bg-secondary/60 transition hover:ring-1 hover:ring-primary/40',
        !style && 'w-full',
      )}
    >
      {medium.urls.thumb ? (
        <img
          src={medium.urls.thumb}
          alt=""
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
        />
      ) : (
        // No preview yet: Huginn is still working, and saying so beats an empty tile.
        <span className="flex h-full w-full items-center justify-center text-muted-foreground">
          <Symbol name="history" size={20} />
        </span>
      )}

      {medium.kind === 'video' && <VideoMark seconds={medium.duration_seconds} />}

      {note && (
        <span className="absolute right-1 top-1 rounded-badge bg-accent/90 px-1.5 py-0.5 text-3xs font-medium text-accent-foreground">
          {note}
        </span>
      )}

      {medium.date_is_estimated && (
        <span
          className="absolute left-1 top-1 rounded-badge bg-background/60 px-1 text-3xs text-muted-foreground"
          title={t('media.estimated')}
        >
          ≈
        </span>
      )}
    </button>
  )
}

/**
 * The grid before its media: tiles of the size the real ones will have, in the same columns and
 * with the same gap, so the page does not jump from a line of text to a screen of pictures.
 * Where the count is known already - an album carries it in its header - it takes that many.
 */
export function MediaGridLoading({
  columns,
  tiles,
}: {
  columns: number
  tiles?: number | undefined
}) {
  // From six columns on, the tiles are large enough that four rows already fill the screen.
  const most = columns * (columns < 6 ? LOADING_ROWS : LOADING_ROWS_WIDE)

  return (
    // The real grid is virtualised and counts one gap below its last row in its height; here
    // that has to be padding, because a margin would collapse out of the section.
    <div
      className="grid gap-1.5 pb-1.5"
      style={{ gridTemplateColumns: `repeat(${String(columns)}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: Math.min(tiles ?? most, most) }, (_, index) => (
        <Placeholder key={index} className="aspect-square w-full" />
      ))}
    </div>
  )
}
