import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import type { Medium } from '@/features/albums/use-albums'
import { downloadOriginal } from '@/features/media/original'
import { REACTIONS } from '@/features/social/reactions'
import { useSocial, useToggleFavorite, useToggleLike } from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/** How long the chrome stays after the last sign of life. */
const REST_MS = 5000

interface ChromeProps {
  medium: Medium
  /** Where in the album this one stands, for the counter. */
  position: { index: number; total: number }
  onBack: () => void
  onComments: () => void
  onInfo: () => void
  /** Heart, star and the conversation only where a query client is. */
  social: boolean
  /** A panel stands open beside the picture: then nothing rests and no tap is swallowed. */
  busy?: boolean | undefined
  /** The menu of what the pipeline can do to this medium; admins only. */
  actions?: React.ReactNode
  /** Offered where a search brought one here: more pictures like this one. */
  onSimilar?: (() => void) | undefined
}

/**
 * What lies over the picture: where one came from, what is in it, and what one can do with it.
 *
 * It rests. Five seconds after the last sign of life everything fades, so a picture is a
 * picture; a moved mouse brings it back on the desktop, a tap does on a phone. The tap that
 * brings it back does nothing else - revealing a video would otherwise stop it.
 */
export function ViewerChrome({
  medium,
  position,
  onBack,
  onComments,
  onInfo,
  social,
  busy = false,
  actions,
  onSimilar,
}: ChromeProps) {
  const [awake, setAwake] = useState(true)
  const [emojis, setEmojis] = useState(false)
  const sleep = useRef<number | undefined>(undefined)

  // Every sign of life puts the rest off; the chrome goes when nothing has happened for a while.
  /** Arm the rest, without saying anything about now: the chrome starts awake by itself. */
  const rest = useCallback(() => {
    window.clearTimeout(sleep.current)
    sleep.current = window.setTimeout(() => {
      setAwake(false)
      setEmojis(false)
    }, REST_MS)
  }, [])

  const stir = useCallback(() => {
    setAwake(true)
    rest()
  }, [rest])

  useEffect(() => {
    // While the details or the conversation are open, one is reading and answering, not
    // looking at a picture: the chrome has no business fading away under that.
    if (busy) {
      window.clearTimeout(sleep.current)
      return undefined
    }
    rest()
    window.addEventListener('pointermove', stir)
    window.addEventListener('keydown', stir)
    return () => {
      window.clearTimeout(sleep.current)
      window.removeEventListener('pointermove', stir)
      window.removeEventListener('keydown', stir)
    }
  }, [busy, medium.id, rest, stir])

  // A finger has no way of moving without touching, so the tap that brings the chrome back is
  // spent on that alone - the next one zooms the picture or stops the video. A mouse usually
  // never gets here, because moving wakes the chrome long before anything is clicked; where it
  // does - a window just focused, or a browser pretending to be a phone - a click does it too.
  const shown = awake || busy

  useEffect(() => {
    if (shown) return
    const wake = (event: PointerEvent) => {
      // A tap inside a panel, a dialog or a menu is meant for what it lands on - a name being
      // corrected, a comment being written. Only the picture's own taps wake the chrome.
      const target = event.target
      if (
        target instanceof Element &&
        target.closest(
          '[data-viewer-panel], [role="dialog"], [role="menu"], [data-radix-popper-content-wrapper]',
        )
      ) {
        return
      }
      event.stopPropagation()
      event.preventDefault()
      stir()
      const swallow = (next: Event) => {
        next.stopPropagation()
        next.preventDefault()
      }
      window.addEventListener('pointerup', swallow, { capture: true, once: true })
      window.addEventListener('click', swallow, { capture: true, once: true })
      window.setTimeout(() => {
        window.removeEventListener('pointerup', swallow, { capture: true })
        window.removeEventListener('click', swallow, { capture: true })
      }, 600)
    }
    window.addEventListener('pointerdown', wake, true)
    return () => {
      window.removeEventListener('pointerdown', wake, true)
    }
  }, [shown, stir])

  return (
    <div
      data-viewer-chrome
      className={cn(
        'pointer-events-none absolute inset-0 z-[1580] transition-opacity duration-300 motion-reduce:transition-none',
        shown ? 'opacity-100' : 'opacity-0',
      )}
      aria-hidden={!shown}
    >
      <Top
        awake={shown}
        position={position}
        onBack={onBack}
        actions={actions}
        title={medium.origin.filename}
      />

      {/* The way through the album, for a screen with a mouse. */}
      {/* A video draws its own controls along its bottom edge. Ours keep out of their way
          rather than sitting on top of them. */}
      <div
        className={cn(
          'pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/55 to-transparent pt-10',
          medium.kind === 'video'
            ? 'pb-[calc(max(env(safe-area-inset-bottom),12px)+56px)]'
            : 'pb-[max(env(safe-area-inset-bottom),12px)]',
        )}
      >
        <div
          className={cn(
            'mx-auto flex w-full max-w-[720px] flex-col gap-2 px-4',
            shown ? 'pointer-events-auto' : 'pointer-events-none',
          )}
        >
          <Actions
            medium={medium}
            social={social}
            emojis={emojis}
            onEmojis={() => {
              setEmojis((open) => !open)
            }}
            onComments={onComments}
            onInfo={onInfo}
            onSimilar={onSimilar}
          />
        </div>
      </div>
    </div>
  )
}

function Top({
  awake,
  position,
  onBack,
  actions,
  title,
}: {
  awake: boolean
  position: { index: number; total: number }
  onBack: () => void
  actions: React.ReactNode
  title: string
}) {
  const { t } = useTranslation()

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-3 bg-gradient-to-b from-black/70 to-transparent px-3 pb-10 pt-[max(env(safe-area-inset-top),10px)]">
      <button
        type="button"
        aria-label={t('media.back')}
        title={title}
        className={cn(
          'flex size-11 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/65',
          awake ? 'pointer-events-auto' : 'pointer-events-none',
        )}
        onClick={onBack}
      >
        <Symbol name="arrow_back" size={22} />
      </button>
      <span className="pointer-events-none rounded-full bg-black/40 px-3 py-1 text-xs-plus tabular-nums text-white/80">
        {position.index + 1} / {position.total}
      </span>
      <div
        className={cn(
          'flex size-11 items-center justify-center',
          awake ? 'pointer-events-auto' : 'pointer-events-none',
        )}
      >
        {actions}
      </div>
    </div>
  )
}

function Actions({
  medium,
  social,
  emojis,
  onEmojis,
  onComments,
  onInfo,
  onSimilar,
}: {
  medium: Medium
  social: boolean
  emojis: boolean
  onEmojis: () => void
  onComments: () => void
  onInfo: () => void
  onSimilar?: (() => void) | undefined
}) {
  const { t } = useTranslation()
  const target = { kind: 'media' as const, id: medium.id }
  const state = useSocial(social ? target : undefined).data
  const like = useToggleLike(target)
  const favorite = useToggleFavorite(target)
  const shareable = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  return (
    /*
     * One cluster in the middle, not six buttons pushed to the far corners of the picture.
     * Three groups, in the order one reaches for them: what one feels about a medium, what one
     * wants to know about it, and what one does with it. The pill behind them lifts them off
     * whatever happens to be in the picture at that spot.
     */
    <div className="flex justify-center pt-1">
      <div className="relative flex items-center gap-0.5 rounded-full bg-black/40 px-1.5 backdrop-blur-md">
        {/* The bar belongs to the heart, so it stands over the heart - wherever the row has put
          it, with however many buttons beside it. */}
        <span className="relative">
          {emojis && (
            <div className="absolute -top-12 left-1/2 flex -translate-x-1/2 gap-1 rounded-full bg-black/70 px-2 py-1.5 backdrop-blur-sm">
              {REACTIONS.map((reaction) => {
                const mine = state?.reaction === reaction.key
                return (
                  <button
                    key={reaction.key}
                    type="button"
                    aria-label={reaction.key}
                    aria-pressed={mine}
                    className={cn(
                      'flex size-9 items-center justify-center rounded-full text-[20px] leading-none transition hover:bg-white/15',
                      mine && 'bg-white/20 ring-1 ring-white/40',
                    )}
                    onClick={() => {
                      // The one already given is taken back: the same tap that set it unsets it.
                      like.mutate(mine ? false : reaction.key)
                      onEmojis()
                    }}
                  >
                    {reaction.emoji}
                  </button>
                )
              })}
            </div>
          )}
          <Round
            label={t('social.like')}
            icon="favorite"
            filled={state?.liked}
            count={state?.likes}
            onClick={onEmojis}
          />
        </span>
        <Round
          label={t('comments.title')}
          icon="chat_bubble"
          count={state?.comments}
          onClick={onComments}
        />
        <Round
          label={t(state?.favorite ? 'walhall.remove' : 'walhall.keep')}
          icon="star"
          filled={state?.favorite}
          onClick={() => {
            favorite.mutate(!state?.favorite)
          }}
        />
        <Line />
        <Round label={t('media.info.show')} icon="info" onClick={onInfo} />
        {onSimilar && <Round label={t('media.similar')} icon="image_search" onClick={onSimilar} />}
        <Line />
        {shareable ? (
          <Round
            label={t('media.share')}
            icon="ios_share"
            onClick={() => {
              void navigator.share({ title: medium.origin.filename, url: window.location.href })
            }}
          />
        ) : (
          <Round
            label={t('media.info.download')}
            icon="download"
            onClick={() => {
              downloadOriginal(medium)
            }}
          />
        )}
      </div>
    </div>
  )
}

/** A hairline between two groups of buttons. */
function Line() {
  return <span aria-hidden="true" className="mx-1 h-5 w-px shrink-0 bg-white/20" />
}

function Round({
  label,
  icon,
  count,
  filled = false,
  onClick,
}: {
  label: string
  icon: string
  count?: number | undefined
  filled?: boolean | undefined
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="flex h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-full px-2.5 text-white transition hover:bg-white/15"
      onClick={onClick}
    >
      <Symbol name={icon} size={22} filled={filled} />
      {count !== undefined && count > 0 && (
        <span className="text-xs-plus tabular-nums">{count}</span>
      )}
    </button>
  )
}
