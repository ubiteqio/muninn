import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { CollectionFrame } from '@/features/albums/collection-frame'
import { type Chapter, spanOf } from '@/features/smarts/use-smarts'
import { cn } from '@/lib/utils'

/**
 * One chapter as a card.
 *
 * A chapter holds pictures, so it is framed like everything else that holds pictures - an album,
 * a month, a year: the square cover inset in its mat, the name inside the frame, the count in
 * the corner. Only a photograph itself goes edge to edge. The cover is built the way an album's
 * is, from up to four of the pictures, so a chapter and a folder are the same kind of object at
 * a glance and differ in what they say, not in how they look.
 */
export function ChapterCard({ chapter }: { chapter: Chapter }) {
  const { t } = useTranslation()
  const title = chapter.title || t('smarts.unnamed')
  const note = [chapter.album_title, spanOf(chapter)].filter(Boolean).join(' · ')

  return (
    <Link
      to="/smarts/$chapterId"
      params={{ chapterId: chapter.id }}
      aria-label={t('smarts.openChapter', { title, count: chapter.size })}
      className="group block text-left"
    >
      <CollectionFrame title={title} note={note}>
        <ChapterCover chapter={chapter} />
        {chapter.size > 0 && (
          <Badge variant="count" className="absolute bottom-1.5 right-1.5">
            {chapter.size}
          </Badge>
        )}
      </CollectionFrame>
    </Link>
  )
}

/**
 * What sits on a chapter's tile: its clearest pictures, the leader first.
 *
 * The same shapes an album's cover uses - one fills the tile, two share it, three put the first
 * beside two smaller ones, four make a square - because it is the same kind of thing.
 */
function ChapterCover({ chapter }: { chapter: Chapter }) {
  const covers = chapter.cover.slice(0, 4)

  if (covers.length === 0) {
    return (
      <span className="flex h-full w-full items-center justify-center text-muted-foreground">
        <Symbol name="auto_awesome" size={28} />
      </span>
    )
  }

  return (
    <span
      className={cn(
        'grid h-full w-full gap-px',
        covers.length > 1 && 'grid-cols-2',
        covers.length > 2 && 'grid-rows-2',
      )}
    >
      {covers.map((medium, index) =>
        medium.urls.thumb ? (
          <img
            key={medium.id}
            src={medium.urls.thumb}
            alt=""
            loading="lazy"
            decoding="async"
            className={cn(
              'h-full w-full object-cover',
              // Three pictures: the first one takes the whole left half.
              covers.length === 3 && index === 0 && 'row-span-2',
            )}
          />
        ) : (
          <span key={medium.id} className="h-full w-full bg-secondary/60" />
        ),
      )}
    </span>
  )
}

/** A card's shape before its chapter is there, so the wall does not arrive in steps. */
export function ChapterCardLoading() {
  return (
    <div className="rounded-xl border border-hairline/10 bg-secondary/45 p-1.5">
      <div className="placeholder aspect-square w-full rounded-lg bg-secondary/60" />
      <div className="mt-2 h-4 w-2/3 animate-pulse rounded bg-secondary/60" />
      <div className="mb-1 mt-1.5 h-3 w-1/2 animate-pulse rounded bg-secondary/40" />
    </div>
  )
}
