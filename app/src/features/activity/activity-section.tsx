import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { HappeningAvatar, HappeningLink } from '@/features/activity/happening'
import { useHappeningText } from '@/features/activity/happening-text'
import { type Happening, useActivity } from '@/features/notify/use-notifications'
import { when } from '@/features/social/when'

/** The start page shows only the latest few; "Alle ansehen" leads to the whole feed. */
const SHOWN = 5

function ActivityRow({ item, thumbSize }: { item: Happening; thumbSize: number }) {
  const text = useHappeningText(item)

  return (
    <HappeningLink
      item={item}
      className="flex w-full items-center gap-3 p-3 text-left transition hover:bg-secondary/40"
    >
      <HappeningAvatar item={item} />

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
    </HappeningLink>
  )
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
      <SectionHeading
        id="activity-heading"
        title={t('activity.title')}
        action={
          <Link to="/activity" className="text-sm font-medium text-primary hover:text-accent">
            {t('common.showAll')}
          </Link>
        }
      />
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
    <LoadingBody boxed={false} className="mt-3">
      <Card className="overflow-hidden">
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
