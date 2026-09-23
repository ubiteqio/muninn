import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { useFavoriteMedia } from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/** How many kept pictures the start screen shows before "Alle ansehen". */
const SHOWN = 8

/**
 * How many squares stand there while they are counted. One row, not the eight the section can
 * hold: nobody knows yet whether anything was kept at all, and a row is as close to a sentence
 * saying nothing was as it is to a section that is full.
 */
const WAITING = 4

/**
 * Walhall on the start screen: the pictures one kept last, as a row to jump into. The whole of
 * it is one tap away; before anything is kept, one sentence says how it fills.
 */
export function WalhallSection({ layout = 'scroller' }: { layout?: 'scroller' | 'grid' }) {
  const { t } = useTranslation()
  const kept = useFavoriteMedia(SHOWN)
  const media = kept.data?.pages[0]?.items ?? []

  return (
    <section aria-labelledby="walhall-heading" aria-busy={kept.isPending}>
      <SectionHeading
        id="walhall-heading"
        title={t('walhall.title')}
        className={layout === 'scroller' ? 'px-5 lg:px-0' : undefined}
        action={
          <Link to="/favorites" className="text-sm font-medium text-primary hover:text-accent">
            {t('walhall.all')}
          </Link>
        }
      />
      {kept.isPending ? (
        <LoadingBody
          boxed={false}
          className={cn(
            'mt-3',
            layout === 'scroller'
              ? 'flex gap-2 overflow-hidden px-5'
              : 'grid grid-cols-4 gap-1.5',
          )}
        >
          {Array.from({ length: WAITING }, (_, index) => (
            <Placeholder
              key={index}
              className={cn(
                'aspect-square',
                layout === 'scroller' ? 'w-[88px] shrink-0' : 'w-full',
              )}
            />
          ))}
        </LoadingBody>
      ) : kept.isSuccess && media.length === 0 ? (
        <EmptyNote className={cn(layout === 'scroller' && 'mx-5 lg:mx-0')}>
          {t('walhall.empty')}
        </EmptyNote>
      ) : (
        <div
          className={cn(
            'mt-3',
            layout === 'scroller'
              ? 'scroll-snap-x flex scroll-px-5 gap-2 overflow-x-auto px-5'
              : 'grid grid-cols-4 gap-1.5',
          )}
        >
          {media.map((medium) => (
            <Link
              key={medium.id}
              to="/favorites"
              search={{ medium: medium.id }}
              aria-label={t('walhall.open')}
              className={cn(
                'block aspect-square overflow-hidden rounded-md bg-secondary/60',
                layout === 'scroller' && 'w-[88px] shrink-0 snap-start',
              )}
            >
              {medium.urls.thumb && (
                <img
                  src={medium.urls.thumb}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              )}
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
