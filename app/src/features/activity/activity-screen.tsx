import { Link } from '@tanstack/react-router'
import { type ReactNode, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { useScrollContainer } from '@/components/layout/scroll-container'
import { EmptyNote } from '@/components/muninn/empty-note'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Card } from '@/components/ui/card'
import { HappeningAvatar } from '@/features/activity/happening'
import { useHappeningText } from '@/features/activity/happening-text'
import { VideoMark } from '@/features/media/video-mark'
import { type Happening, useActivityFeed } from '@/features/notify/use-notifications'
import { emojiOf } from '@/features/social/reactions'
import { when } from '@/features/social/when'
import { cn } from '@/lib/utils'

type Picture = Happening['previews'][number]

/** How far ahead of the end the next page is asked for, so scrolling never meets the bottom. */
const AHEAD = '800px'

/** The entries that stand there while the first page is on its way: about a screenful. */
const WAITING = 3

/** The local calendar day, as the feed groups by it. */
function dayOf(iso: string): string {
  const date = new Date(iso)
  return `${String(date.getFullYear())}-${String(date.getMonth() + 1)}-${String(date.getDate())}`
}

/** Consecutive happenings of one day under one heading; the list arrives newest first. */
function byDay(items: Happening[]): { day: string; items: Happening[] }[] {
  const days: { day: string; items: Happening[] }[] = []
  for (const item of items) {
    const day = dayOf(item.at)
    const last = days.at(-1)
    if (last?.day === day) last.items.push(item)
    else days.push({ day, items: [item] })
  }
  return days
}

/** "Heute", "Gestern", then the weekday and the date, with the year once it is not this one. */
function useDayTitle(): (iso: string) => string {
  const { t, i18n } = useTranslation()
  return (iso: string) => {
    const now = new Date()
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
    if (dayOf(iso) === dayOf(now.toISOString())) return t('activity.today')
    if (dayOf(iso) === dayOf(yesterday.toISOString())) return t('activity.yesterday')
    const date = new Date(iso)
    return date.toLocaleDateString(i18n.language, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      ...(date.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
    })
  }
}

/** Today says how long ago, like a chat; an older day has its heading, so the clock is enough. */
function useMoment(): (iso: string) => string {
  const { i18n } = useTranslation()
  return (iso: string) =>
    dayOf(iso) === dayOf(new Date().toISOString())
      ? when(iso)
      : new Date(iso).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
}

/** One picture of a post, the larger copy where there is one, leading to it in its album. */
function PictureTile({
  picture,
  className,
  children,
}: {
  picture: Picture
  className?: string | undefined
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const source = picture.preview ?? picture.thumb
  return (
    <Link
      to="/albums/$albumId"
      params={{ albumId: picture.album_id }}
      search={{ medium: picture.id }}
      aria-label={t(picture.kind === 'video' ? 'activity.openVideo' : 'activity.openPicture')}
      className={cn('relative block overflow-hidden bg-secondary', className)}
    >
      {source && (
        <img
          src={source}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover transition duration-300 hover:scale-[1.02]"
        />
      )}
      {picture.kind === 'video' && <VideoMark seconds={null} />}
      {children}
    </Link>
  )
}

/**
 * What a post shows: the one picture it is about, large, or a batch of new ones as a grid whose
 * last tile counts the rest.
 */
function PostPictures({ item }: { item: Happening }) {
  const { t } = useTranslation()
  const pictures = item.previews
  const first = pictures[0]
  if (!first) return null

  if (item.kind !== 'new_media' || pictures.length === 1) {
    return (
      <PictureTile picture={first} className="aspect-[4/3] w-full rounded-lg">
        {item.kind === 'like' && (
          <span
            aria-hidden="true"
            className="absolute bottom-2 left-2 flex h-8 min-w-8 items-center justify-center rounded-full bg-black/45 px-2 text-base text-white backdrop-blur-[2px]"
          >
            {emojiOf(item.reaction ?? 'heart')}
          </span>
        )}
      </PictureTile>
    )
  }

  const rest = item.count - pictures.length
  return (
    <div className="grid grid-cols-2 gap-1 overflow-hidden rounded-lg">
      {pictures.map((picture, index) => {
        const last = index === pictures.length - 1
        return (
          <PictureTile
            key={picture.id}
            picture={picture}
            className={cn(
              pictures.length === 3 && index === 0 ? 'col-span-2 aspect-[2/1]' : 'aspect-square',
            )}
          >
            {last && rest > 0 && (
              <span className="absolute inset-0 flex items-center justify-center bg-black/45 text-xl font-semibold text-white">
                <span aria-hidden="true">+{rest}</span>
                <span className="sr-only">{t('activity.more', { count: rest })}</span>
              </span>
            )}
          </PictureTile>
        )
      })}
    </div>
  )
}

/** One post on the line: who and what at the top, what was said, then the pictures. */
function Post({ item }: { item: Happening }) {
  const text = useHappeningText(item)
  const moment = useMoment()

  return (
    <li className="relative flex gap-3">
      {/* The mark sits on the line, the card hangs off it. */}
      <div className="z-10 pt-3">
        <HappeningAvatar item={item} />
      </div>

      <Card className="min-w-0 flex-1 overflow-hidden">
        <div className="space-y-3 p-3">
          <div className="min-w-0">
            <p className="text-base-plus text-foreground">
              {item.actor && <span className="font-semibold">{item.actor} </span>}
              {text}
            </p>
            <p className="truncate text-xs-plus text-muted-foreground">
              {item.album && (
                <>
                  <Link
                    to="/albums/$albumId"
                    params={{ albumId: item.album.id }}
                    className="font-medium hover:text-foreground hover:underline"
                  >
                    {item.album.title}
                  </Link>
                  {' · '}
                </>
              )}
              <time dateTime={item.at}>{moment(item.at)}</time>
            </p>
          </div>

          {item.excerpt && (
            <blockquote className="whitespace-pre-line break-words rounded-lg rounded-tl-sm bg-secondary/60 px-3 py-2 text-base text-foreground">
              {item.excerpt}
            </blockquote>
          )}

          <PostPictures item={item} />
        </div>
      </Card>
    </li>
  )
}

/** The line the posts of a day hang on, running behind the round marks. */
const LINE =
  'relative space-y-4 before:absolute before:bottom-0 before:left-[18.5px] before:top-0 before:w-px before:bg-hairline/15'

/** A post on its way, in the shape of one with a picture: the commonest kind. */
function PostLoading() {
  return (
    <li className="relative flex gap-3">
      <div className="z-10 pt-3">
        <Placeholder className="size-[38px] rounded-full" />
      </div>
      <Card className="min-w-0 flex-1 space-y-3 p-3">
        <div className="space-y-2">
          <Placeholder className="h-4 w-3/4" />
          <Placeholder className="h-3 w-1/3" />
        </div>
        <Placeholder className="aspect-[4/3] w-full rounded-lg" />
      </Card>
    </li>
  )
}

/**
 * Neuigkeiten as a feed: everything the family has done, newest first, grouped by day on a
 * timeline. Each post leads to where it happened; the next page is asked for before the end is
 * reached, and the feed follows the live channel like the card on the start page.
 */
export function ActivityScreen() {
  const { t } = useTranslation()
  const feed = useActivityFeed()
  const dayTitle = useDayTitle()
  const container = useScrollContainer()
  const end = useRef<HTMLDivElement>(null)

  const items = useMemo(() => feed.data?.pages.flatMap((page) => page.items) ?? [], [feed.data])
  const days = useMemo(() => byDay(items), [items])

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feed
  useEffect(() => {
    const target = end.current
    if (!target || !hasNextPage) return
    const watcher = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting) && !isFetchingNextPage) {
          void fetchNextPage()
        }
      },
      { root: container, rootMargin: `0px 0px ${AHEAD} 0px` },
    )
    watcher.observe(target)
    return () => {
      watcher.disconnect()
    }
  }, [container, hasNextPage, isFetchingNextPage, fetchNextPage])

  return (
    <AppShell title={t('activity.title')} active="home">
      <div
        className="mx-auto w-full max-w-[600px] space-y-6 px-5 pb-8 md:px-0"
        aria-busy={feed.isPending}
      >
        <p className="text-base text-muted-foreground">{t('activity.description')}</p>

        {feed.isPending ? (
          <LoadingBody boxed={false} className="space-y-3">
            <Placeholder className="h-3 w-24" />
            <ol className={LINE}>
              {Array.from({ length: WAITING }, (_, index) => (
                <PostLoading key={index} />
              ))}
            </ol>
          </LoadingBody>
        ) : feed.isSuccess && items.length === 0 ? (
          <EmptyNote>{t('activity.empty')}</EmptyNote>
        ) : (
          days.map(({ day, items: posts }) => {
            const first = posts[0]
            if (!first) return null
            return (
              <section key={day} aria-labelledby={`activity-${day}`}>
                <SectionHeading id={`activity-${day}`} title={dayTitle(first.at)} />
                <ol className={cn('mt-3', LINE)}>
                  {posts.map((item) => (
                    <Post key={item.key} item={item} />
                  ))}
                </ol>
              </section>
            )
          })
        )}

        {isFetchingNextPage && (
          <LoadingBody boxed={false}>
            <ol className={LINE}>
              <PostLoading />
            </ol>
          </LoadingBody>
        )}
        <div ref={end} aria-hidden="true" />
      </div>
    </AppShell>
  )
}
