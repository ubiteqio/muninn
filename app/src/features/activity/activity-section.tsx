import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { PersonInitial } from '@/components/muninn/person-initial'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { type Happening, useActivity } from '@/features/notify/use-notifications'
import { emojiOf } from '@/features/social/reactions'
import { when } from '@/features/social/when'
import { cn } from '@/lib/utils'

/** The start page shows only the latest few; the bell keeps the rest. */
const SHOWN = 5

const KIND_ICON: Record<string, string> = {
  comment: 'chat_bubble',
  like: 'favorite',
  new_media: 'add_photo_alternate',
}

/** Who did it, or the album's own mark when nobody did - new pictures simply arrive. */
function Initial({ name }: { name: string | null | undefined }) {
  if (!name) {
    return (
      <span className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-secondary text-muted-foreground">
        <Symbol name="photo_library" size={18} />
      </span>
    )
  }
  return <PersonInitial name={name} size={38} />
}

function ActivityRow({ item, thumbSize }: { item: Happening; thumbSize: number }) {
  const { t } = useTranslation()
  const reacted = item.kind === 'like' && item.reaction && item.reaction !== 'heart'
  const text =
    item.kind === 'new_media'
      ? t('activity.kind.new_media', { count: item.count })
      : reacted
        ? t('activity.kind.reaction', { emoji: emojiOf(item.reaction) })
        : t(`activity.kind.${item.kind}`)

  const body = (
    <>
      <div className="relative shrink-0">
        <Initial name={item.actor} />
        {/* What happened, overlapping the initial at the bottom right. */}
        <span className="absolute -bottom-0.5 -right-0.5 flex h-[19px] w-[19px] items-center justify-center rounded-full border-2 border-card bg-secondary">
          {reacted ? (
            <span aria-hidden="true" className="text-[10px] leading-none">
              {emojiOf(item.reaction)}
            </span>
          ) : (
            <Symbol
              name={KIND_ICON[item.kind] ?? 'history'}
              size={11}
              filled={item.kind === 'like'}
              className={item.kind === 'like' ? 'text-rose-500' : 'text-muted-foreground'}
            />
          )}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-base-plus text-foreground">
          {item.actor && <span className="font-semibold">{item.actor} </span>}
          {text}
        </p>
        {item.excerpt && (
          <p className="truncate text-xs-plus text-muted-foreground">„{item.excerpt}“</p>
        )}
        <p className="truncate text-xs-plus text-muted-foreground">
          {item.album?.title}
          {item.album && ' · '}
          {when(item.at)}
        </p>
      </div>

      {item.media?.thumb && (
        <img
          src={item.media.thumb}
          alt=""
          loading="lazy"
          className="shrink-0 rounded-thumb object-cover"
          style={{ width: thumbSize, height: thumbSize }}
        />
      )}
    </>
  )
  const row = 'flex w-full items-center gap-3 p-3 text-left transition hover:bg-secondary/40'

  if (item.media && item.kind !== 'new_media') {
    return (
      <Link
        to="/albums/$albumId"
        params={{ albumId: item.media.album_id }}
        search={{ medium: item.media.id }}
        className={row}
      >
        {body}
      </Link>
    )
  }
  const albumId = item.album?.id ?? item.media?.album_id
  if (albumId) {
    return (
      <Link to="/albums/$albumId" params={{ albumId }} className={row}>
        {body}
      </Link>
    )
  }
  return <div className={cn(row, 'cursor-default')}>{body}</div>
}

/**
 * Neuigkeiten: what the family has been up to - comments, likes and new pictures, newest first,
 * each a way to where it happened. It follows the live channel.
 */
export function ActivitySection({
  thumbSize = 42,
}: {
  /** 42 px on mobile, 44 px in the desktop aside. */
  thumbSize?: number
}) {
  const { t } = useTranslation()
  const activity = useActivity(SHOWN)
  const items = activity.data?.items ?? []

  return (
    <section aria-labelledby="activity-heading" aria-busy={activity.isPending}>
      <SectionHeading id="activity-heading" title={t('activity.title')} />
      {activity.isPending ? (
        <ActivityLoading thumbSize={thumbSize} />
      ) : activity.isSuccess && items.length === 0 ? (
        <EmptyNote>{t('activity.empty')}</EmptyNote>
      ) : (
        items.length > 0 && (
          <Card className="mt-3 overflow-hidden">
            {items.map((item, index) => (
              <div key={item.key}>
                {index > 0 && <Separator />}
                <ActivityRow item={item} thumbSize={thumbSize} />
              </div>
            ))}
          </Card>
        )
      )}
    </section>
  )
}

/**
 * The card of the latest few, before they are there: a row per entry, with the round mark, the
 * two lines of words and the picture it happened to, all in the sizes the real rows use.
 */
function ActivityLoading({ thumbSize }: { thumbSize: number }) {
  return (
    <LoadingBody boxed={false}>
      <Card className="mt-3 overflow-hidden">
        {Array.from({ length: SHOWN }, (_, index) => (
          <div key={index}>
            {index > 0 && <Separator />}
            <div className="flex items-center gap-3 p-3">
              <Placeholder className="size-[38px] shrink-0 rounded-full" />
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <Placeholder className="h-4 w-3/4" />
                <Placeholder className="h-3 w-1/2" />
              </div>
              <Placeholder
                className="shrink-0 rounded-thumb"
                style={{ width: thumbSize, height: thumbSize }}
              />
            </div>
          </div>
        ))}
      </Card>
    </LoadingBody>
  )
}
