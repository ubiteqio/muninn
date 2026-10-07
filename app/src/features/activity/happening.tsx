import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { PersonInitial } from '@/components/muninn/person-initial'
import { Symbol } from '@/components/muninn/symbol'
import { reactedWith } from '@/features/activity/happening-text'
import type { Happening } from '@/features/notify/use-notifications'
import { emojiOf } from '@/features/social/reactions'

/**
 * What the start page's news card and the news feed share: who did it and where it leads. What
 * it says is in happening-text.ts.
 */

const KIND_ICON: Record<string, string> = {
  comment: 'chat_bubble',
  like: 'favorite',
  new_media: 'add_photo_alternate',
}

/**
 * Who did it, or the album's own mark when nobody did - new pictures simply arrive. What
 * happened overlaps it at the bottom right.
 */
export function HappeningAvatar({ item }: { item: Happening }) {
  const reaction = reactedWith(item)
  return (
    <div className="relative shrink-0">
      {item.actor ? (
        <PersonInitial name={item.actor} size={38} />
      ) : (
        <span className="flex h-[38px] w-[38px] items-center justify-center rounded-full bg-secondary text-muted-foreground">
          <Symbol name="photo_library" size={18} />
        </span>
      )}
      <span className="absolute -bottom-0.5 -right-0.5 flex h-[19px] w-[19px] items-center justify-center rounded-full border-2 border-card bg-secondary">
        {reaction ? (
          <span aria-hidden="true" className="text-[10px] leading-none">
            {emojiOf(reaction)}
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
  )
}

/**
 * Where a happening leads: a comment or a like to the picture in its album, new pictures to the
 * album they arrived in. Nothing to lead to - an album gone since - leaves it a plain block.
 */
export function HappeningLink({
  item,
  className,
  children,
}: {
  item: Happening
  className?: string | undefined
  children: ReactNode
}) {
  if (item.media && item.kind !== 'new_media') {
    return (
      <Link
        to="/albums/$albumId"
        params={{ albumId: item.media.album_id }}
        search={{ medium: item.media.id }}
        className={className}
      >
        {children}
      </Link>
    )
  }
  const albumId = item.album?.id ?? item.media?.album_id
  if (albumId) {
    return (
      <Link to="/albums/$albumId" params={{ albumId }} className={className}>
        {children}
      </Link>
    )
  }
  return <div className={className}>{children}</div>
}
