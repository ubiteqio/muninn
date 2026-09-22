import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { CommentsSection } from '@/features/social/comments'
import { likedBy } from '@/features/social/liked-by'
import { useSocial, useToggleFavorite, useToggleLike } from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/**
 * Heart, speech bubble and star of an album, as one calm row under its title - pills with their
 * numbers, like a message thread's reactions. The speech bubble unfolds the album's
 * conversation right below.
 */
export function AlbumSocial({ albumId }: { albumId: string }) {
  const { t } = useTranslation()
  const target = { kind: 'album' as const, id: albumId }
  const social = useSocial(target)
  const like = useToggleLike(target)
  const favorite = useToggleFavorite(target)
  const [talking, setTalking] = useState(false)
  const state = social.data
  const liked = state?.liked ?? false
  const kept = state?.favorite ?? false

  return (
    <div>
      <div
        role="group"
        aria-label={t('social.actions')}
        className="flex flex-wrap items-center gap-2"
      >
        <Pill
          label={t(liked ? 'social.unlike' : 'social.like')}
          title={state ? likedBy(state, t) || t('social.like') : undefined}
          pressed={liked}
          disabled={!state || like.isPending}
          onClick={() => {
            like.mutate(!liked)
          }}
        >
          <Symbol
            name="favorite"
            size={17}
            filled={liked}
            className={cn(liked && 'text-rose-500')}
          />
          {state && state.likes > 0 && <span className="tabular-nums">{state.likes}</span>}
        </Pill>
        <Pill
          label={t('comments.title')}
          pressed={talking}
          onClick={() => {
            setTalking(!talking)
          }}
        >
          <Symbol name="chat_bubble" size={16} />
          {state && state.comments > 0 && <span className="tabular-nums">{state.comments}</span>}
        </Pill>
        <Pill
          label={t(kept ? 'social.unfavorite' : 'social.favorite')}
          pressed={kept}
          disabled={!state || favorite.isPending}
          onClick={() => {
            favorite.mutate(!kept)
          }}
        >
          <Symbol name="star" size={17} filled={kept} className={cn(kept && 'text-accent')} />
        </Pill>
      </div>

      {talking && (
        <div className="mt-4 max-w-[560px]">
          <CommentsSection target={target} />
        </div>
      )}
    </div>
  )
}

function Pill({
  label,
  title,
  pressed,
  disabled = false,
  onClick,
  children,
}: {
  label: string
  title?: string | undefined
  pressed: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs-plus transition disabled:opacity-60',
        pressed
          ? 'border-accent/40 bg-accent/10 text-foreground'
          : 'border-hairline/15 text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}
