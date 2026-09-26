import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { type Chapter, spanOf } from '@/features/smarts/use-smarts'
import { cn } from '@/lib/utils'

/**
 * One chapter as a card: a collage of its clearest pictures, its name and how much is in it.
 *
 * The collage is the point. A name like "Katze · Tier · Innenraum" says what the group is, but
 * six pictures say it faster - and a card one wants to open is a card that shows something.
 * The first picture is the leader of the group, the one everything else was measured against,
 * so it stands large; the others are the next closest to it.
 */
export function ChapterCard({ chapter, large = false }: { chapter: Chapter; large?: boolean }) {
  const { t } = useTranslation()
  const [first, ...rest] = chapter.cover
  const beside = rest.slice(0, large ? 4 : 2)
  const title = chapter.title || t('smarts.unnamed')

  return (
    <Link
      to="/smarts/$chapterId"
      params={{ chapterId: chapter.id }}
      aria-label={t('smarts.openChapter', { title, count: chapter.size })}
      className={cn(
        'group relative flex flex-col overflow-hidden rounded-xl border border-hairline/[0.08] bg-card transition',
        'hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[0_14px_30px_-18px_rgba(0,0,0,0.6)]',
        large && 'sm:col-span-2',
      )}
    >
      <div className={cn('flex gap-0.5', large ? 'h-44 sm:h-52' : 'h-36')}>
        <Cover medium={first} className="flex-[2]" />
        {beside.length > 0 && (
          <div className={cn('flex flex-1 flex-col gap-0.5', large && 'sm:flex-row')}>
            {beside.map((medium) => (
              <Cover key={medium.id} medium={medium} className="flex-1" />
            ))}
          </div>
        )}

        {/* The count sits on the pictures, where the eye already is. */}
        <span className="absolute right-2 top-2 rounded-badge bg-background/75 px-2 py-0.5 text-2xs font-semibold tabular-nums text-foreground backdrop-blur-sm">
          {chapter.size}
        </span>

        {/* A chapter can be watched instead of scrolled: the button says so on hover, and is
            always there for a finger, which has no hover. */}
        <span className="pointer-events-none absolute bottom-[4.6rem] right-2 flex h-9 w-9 items-center justify-center rounded-full bg-primary/90 text-primary-foreground opacity-0 shadow-lg transition group-hover:opacity-100 max-md:opacity-90">
          <Symbol name="play_arrow" size={20} filled />
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-1 px-3 py-2.5">
        <p className="truncate text-base font-semibold text-foreground">{title}</p>
        <p className="truncate text-2xs text-muted-foreground">
          {chapter.album_title}
          {spanOf(chapter) && ` · ${spanOf(chapter)}`}
        </p>
      </div>
    </Link>
  )
}

function Cover({
  medium,
  className,
}: {
  medium: Chapter['cover'][number] | undefined
  className?: string
}) {
  if (!medium?.urls.thumb) {
    return <span className={cn('bg-secondary/60', className)} />
  }
  return (
    <img
      src={medium.urls.thumb}
      alt=""
      loading="lazy"
      decoding="async"
      className={cn('h-full w-full object-cover', className)}
    />
  )
}

/** A card's shape before its chapter is there, so the mosaic does not arrive in steps. */
export function ChapterCardLoading({ large = false }: { large?: boolean }) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border border-hairline/[0.08] bg-card',
        large && 'sm:col-span-2',
      )}
    >
      <div className={cn('animate-pulse bg-secondary/60', large ? 'h-44 sm:h-52' : 'h-36')} />
      <div className="space-y-2 px-3 py-3">
        <div className="h-3.5 w-2/3 animate-pulse rounded bg-secondary/60" />
        <div className="h-2.5 w-1/2 animate-pulse rounded bg-secondary/40" />
      </div>
    </div>
  )
}
