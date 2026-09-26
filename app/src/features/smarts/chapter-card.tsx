import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { CollectionFrame } from '@/features/albums/collection-frame'
import { type Chapter, spanOf, titleOf } from '@/features/smarts/use-smarts'
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
  const title = titleOf(chapter, t)
  // Where it comes from and when. What kind it is stands on the cover, so it is not said twice.
  // A theme runs through the years rather than coming from somewhere, and says so.
  const note =
    chapter.kind === 'theme'
      ? t('smarts.overYears', { count: Number(chapter.title_args.years ?? 0) })
      : [
          chapter.albums > 1 ? t('smarts.fromAlbums', { count: chapter.albums }) : null,
          spanOf(chapter),
        ]
          .filter(Boolean)
          .join(' · ')

  return (
    <Link
      to="/smarts/$chapterId"
      params={{ chapterId: chapter.id }}
      aria-label={t('smarts.openChapter', { title, count: chapter.size })}
      className="group block text-left"
    >
      <CollectionFrame title={title} note={note}>
        <ChapterCover chapter={chapter} />
        {/* A breath of shade: the medallion and the count have to be legible over a snow field
            as well as over a night sky. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.38),rgba(0,0,0,0.12)_55%,transparent_75%)] opacity-90 transition-opacity duration-200 group-hover:opacity-60"
        />
        <KindMedallion chapter={chapter} />
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
 * What each kind wears in the middle of its cover.
 *
 * A mark in a corner is a footnote; nobody reads footnotes on a wall of eighty tiles. The
 * medallion sits where the eye lands, large enough to be read across the room, and it is what
 * makes a journey, a face and a feast tell themselves apart before a word is read. It rests at
 * three quarters and comes forward when the pointer does, so the picture underneath is never
 * hidden for long.
 *
 * The colours are Muninn's own: amber for what is warm, gold for the feasts, night blue for
 * the people, frosted parchment for what only needs to be legible.
 */
const THEME_ICON: Record<string, string> = {
  water: 'pool',
  green: 'park',
  sport: 'sports_soccer',
  city: 'location_city',
  animals: 'pets',
  table: 'restaurant',
  wheels: 'directions_bike',
  flowers: 'local_florist',
  snow: 'ac_unit',
  beach: 'beach_access',
  stage: 'music_note',
  paper: 'description',
  sundown: 'wb_twilight',
  playground: 'toys',
  fireworks: 'celebration',
}

const MEDALLION: Record<string, { icon: string; className: string }> = {
  trip: { icon: 'flight', className: 'bg-primary/85 text-primary-foreground' },
  place: { icon: 'place', className: 'bg-background/75 text-foreground' },
  person: { icon: 'face', className: 'bg-secondary/85 text-secondary-foreground' },
  ritual: { icon: 'celebration', className: 'bg-primary/85 text-primary-foreground' },
  motif: { icon: 'auto_awesome', className: 'bg-background/70 text-foreground' },
}

/** Months as a calendar leaf abbreviates them. */
const SHORT_MONTHS = [
  'JAN',
  'FEB',
  'MÄR',
  'APR',
  'MAI',
  'JUN',
  'JUL',
  'AUG',
  'SEP',
  'OKT',
  'NOV',
  'DEZ',
]

/** The values a chapter carries are text and numbers, never objects. */
function textOf(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

/** The mark in the middle of the cover that says what kind of chapter this is. */
function KindMedallion({ chapter }: { chapter: Chapter }) {
  const { t } = useTranslation()
  const kind = t(`smarts.kind.${chapter.kind}`)

  // A day wears the day itself: a torn-off calendar leaf says "Tag" without the word.
  if (chapter.kind === 'day') {
    const iso = textOf(chapter.title_args.day)
    const [year, month, day] = iso.split('-')
    return (
      <span
        aria-label={kind}
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
      >
        <span className="w-[58px] overflow-hidden rounded-xl bg-card/90 text-center shadow-[0_8px_20px_-8px_rgba(0,0,0,0.75)] ring-1 ring-white/15 transition duration-200 group-hover:scale-[1.08] group-hover:bg-card">
          <span className="block bg-primary py-0.5 text-[10px] font-bold tracking-[0.12em] text-primary-foreground">
            {SHORT_MONTHS[Number(month) - 1] ?? ''}
          </span>
          <span className="block pt-1 text-2xl font-bold tabular-nums leading-none text-foreground">
            {Number(day) || ''}
          </span>
          <span className="block pb-1 pt-0.5 text-[9px] font-medium tabular-nums text-muted-foreground">
            {year}
          </span>
        </span>
      </span>
    )
  }

  // A theme wears its own symbol: a pool, a tree, a ball, a cat.
  const medallion =
    chapter.kind === 'theme'
      ? {
          icon: THEME_ICON[chapter.title_key] ?? 'auto_awesome',
          className: 'bg-accent/85 text-accent-foreground',
        }
      : (MEDALLION[chapter.kind] ?? MEDALLION.motif)
  // A journey wears how long it lasted, under its wing.
  const days = chapter.kind === 'trip' ? Number(chapter.title_args.days ?? 0) : 0

  return (
    <span
      aria-label={kind}
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
    >
      <span
        className={cn(
          'flex h-[58px] w-[58px] flex-col items-center justify-center rounded-full shadow-[0_8px_20px_-8px_rgba(0,0,0,0.75)] ring-1 ring-white/15 backdrop-blur-[2px] transition duration-200',
          'opacity-90 group-hover:scale-[1.08] group-hover:opacity-100',
          medallion?.className,
        )}
      >
        <Symbol name={medallion?.icon ?? 'auto_awesome'} size={days ? 24 : 30} filled />
        {days > 0 && (
          <span className="text-[10px] font-bold leading-none">
            {t('smarts.days', { count: days })}
          </span>
        )}
      </span>
    </span>
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
