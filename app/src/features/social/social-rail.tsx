import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { ReactionButton } from '@/features/social/reaction-button'
import {
  type SocialTarget,
  useSocial,
  useToggleFavorite,
  useToggleLike,
} from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/**
 * Heart, speech bubble and star over the picture: a column of round glass buttons at the right
 * edge, above where a video keeps its controls. The numbers sit under the icons, the way phones
 * taught everybody to read them. When the info panel opens beside the picture, the column moves
 * out of its way.
 */
export function SocialRail({
  target,
  shifted,
  onComments,
}: {
  target: SocialTarget
  /** The info panel is open beside the picture (from the tablet up). */
  shifted: boolean
  onComments: () => void
}) {
  const { t } = useTranslation()
  const social = useSocial(target)
  const like = useToggleLike(target)
  const favorite = useToggleFavorite(target)
  const state = social.data
  const liked = state?.liked ?? false
  const kept = state?.favorite ?? false

  return (
    <div
      role="group"
      aria-label={t('social.actions')}
      className={cn(
        'pointer-events-auto absolute bottom-[calc(6rem+env(safe-area-inset-bottom))] right-[max(env(safe-area-inset-right),12px)] z-[1590] flex flex-col items-center gap-3 transition-[right] duration-200 motion-reduce:transition-none',
        shifted && 'md:right-[344px]',
      )}
    >
      {target.kind === 'media' ? (
        <ReactionButton
          state={state}
          pending={like.isPending}
          onReact={(reaction) => {
            like.mutate(reaction ?? false)
          }}
        />
      ) : (
        <RailButton
          label={t(liked ? 'social.unlike' : 'social.like')}
          pressed={liked}
          disabled={!state || like.isPending}
          count={state?.likes}
          onClick={() => {
            like.mutate(!liked)
          }}
        >
          <Symbol
            name="favorite"
            size={24}
            filled={liked}
            className={cn(liked && 'text-rose-500')}
          />
        </RailButton>
      )}
      <RailButton label={t('comments.title')} count={state?.comments} onClick={onComments} toggles>
        <Symbol name="chat_bubble" size={22} />
      </RailButton>
      <RailButton
        label={t(kept ? 'social.unfavorite' : 'social.favorite')}
        pressed={kept}
        disabled={!state || favorite.isPending}
        onClick={() => {
          favorite.mutate(!kept)
        }}
      >
        <Symbol name="star" size={24} filled={kept} className={cn(kept && 'text-accent')} />
      </RailButton>
    </div>
  )
}

function RailButton({
  label,
  pressed,
  disabled = false,
  count,
  onClick,
  toggles = false,
  children,
}: {
  label: string
  pressed?: boolean | undefined
  disabled?: boolean
  count?: number | undefined
  onClick: () => void
  /** Opens and closes a panel of the viewer itself: a tap on it is not a tap beside the panel. */
  toggles?: boolean
  children: React.ReactNode
}) {
  return (
    <span className="flex flex-col items-center gap-0.5">
      <button
        type="button"
        aria-label={label}
        title={label}
        aria-pressed={pressed}
        data-viewer-toggle={toggles ? '' : undefined}
        disabled={disabled}
        onClick={onClick}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-black/40 text-white ring-1 ring-white/15 backdrop-blur-md transition hover:bg-black/55 active:scale-95 disabled:opacity-60"
      >
        {children}
      </button>
      <span
        aria-hidden="true"
        className="min-h-[14px] text-2xs font-medium tabular-nums text-white drop-shadow"
      >
        {count ? count : ''}
      </span>
    </span>
  )
}
