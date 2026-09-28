import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import type { Medium } from '@/features/albums/use-albums'
import { STIRRED } from '@/features/media/stirred'
import { type Handing, useHandOver } from '@/features/media/use-hand-over'
import { REACTIONS } from '@/features/social/reactions'
import { useSocial, useToggleFavorite, useToggleLike } from '@/features/social/use-social'
import { cn } from '@/lib/utils'
import { isNative } from '@/platform/server'

/** How long the chrome stays after the last sign of life. */
const REST_MS = 3000

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
  /** The chrome itself, to tell the viewer's own dialog from one opened on top of it. */
  const root = useRef<HTMLDivElement>(null)

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

  const handOver = useHandOver(medium, stir)

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
    // A video keeps its own taps: the browser draws the controls and answers them, and a phone
    // does not tell the page at all. So the window hears nothing and the buttons would stay
    // away. The viewer listens at the video itself and says so here.
    window.addEventListener(STIRRED, stir)
    return () => {
      window.clearTimeout(sleep.current)
      window.removeEventListener('pointermove', stir)
      window.removeEventListener('keydown', stir)
      window.removeEventListener(STIRRED, stir)
    }
  }, [busy, medium.id, rest, stir])

  // A finger has no way of moving without touching, so the tap that brings the chrome back is
  // spent on that alone - the next one zooms the picture or stops the video. A mouse usually
  // never gets here, because moving wakes the chrome long before anything is clicked; where it
  // does - a window just focused, or a browser pretending to be a phone - a click does it too.
  // Nor while a file is loading to be saved or shared: the spinning button is the only sign.
  const shown = awake || busy || handOver.working !== null

  useEffect(() => {
    if (shown) return
    const wake = (event: PointerEvent) => {
      // A tap inside a panel or a menu is meant for what it lands on - a name being corrected,
      // a comment being written. Only the picture's own taps wake the chrome.
      const target = event.target
      if (!(target instanceof Element)) return
      if (
        target.closest('[data-viewer-panel], [role="menu"], [data-radix-popper-content-wrapper]')
      ) {
        return
      }
      /*
       * The viewer is a dialog itself, and so is every tap that lands on the picture. Turning
       * away from all of them - which is what a bare `[role="dialog"]` did - meant no tap on a
       * picture ever brought the buttons back. Only a dialog opened on top of the viewer, a
       * confirmation or a menu of its own, keeps its taps to itself.
       */
      const dialog = target.closest('[role="dialog"]')
      if (dialog !== null && dialog !== root.current?.closest('[role="dialog"]')) return
      // A video's own controls are the browser's, inside the element itself. Swallowing the
      // first tap there is swallowing play, pause or a drag of the scrubber - and the chrome
      // is not worth that. It wakes, and the tap goes through to them all the same.
      if (target instanceof Element && target.closest('video')) {
        stir()
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
      ref={root}
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

      {/*
       * Down the right-hand edge, under the menu. Along the bottom they sat over the video's
       * own controls and took a strip of every picture with them; standing in a column they
       * cover a hand's width of one edge and the medium has the whole screen.
       */}
      <div
        className={cn(
          'absolute right-2 top-[calc(max(env(safe-area-inset-top),10px)+56px)] flex flex-col items-center gap-1',
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
          handOver={handOver}
        />
      </div>

      {/* Above the video's controls, where a thumb is not. */}
      <div
        role="status"
        className="pointer-events-none absolute inset-x-0 bottom-[calc(env(safe-area-inset-bottom)+120px)] flex justify-center px-4"
      >
        {handOver.news !== null && (
          <span className="rounded-full bg-black/70 px-4 py-2 text-sm text-white backdrop-blur-md">
            {handOver.news}
          </span>
        )}
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
  handOver,
}: {
  medium: Medium
  social: boolean
  emojis: boolean
  onEmojis: () => void
  onComments: () => void
  onInfo: () => void
  onSimilar?: (() => void) | undefined
  handOver: {
    working: Handing | null
    save: () => void
    share: () => void
    shareable: boolean
  }
}) {
  const { t } = useTranslation()
  const target = { kind: 'media' as const, id: medium.id }
  const state = useSocial(social ? target : undefined).data
  const like = useToggleLike(target)
  const favorite = useToggleFavorite(target)
  const native = isNative()

  return (
    /*
     * One column down the edge, not six buttons scattered over the picture. Three groups, in
     * the order one reaches for them: what one feels about a medium, what one wants to know
     * about it, and what one does with it. The pill behind them lifts them off whatever
     * happens to be in the picture at that spot.
     */
    <div className="flex flex-col items-center">
      <div className="relative flex flex-col items-center gap-0.5 rounded-full bg-black/40 py-1.5 backdrop-blur-md">
        {/* The bar belongs to the heart, so it stands beside the heart - wherever the column
          has put it, with however many buttons under it. */}
        <span className="relative">
          {emojis && (
            <div className="absolute right-full top-1/2 mr-2 flex -translate-y-1/2 gap-1 rounded-full bg-black/70 px-2 py-1.5 backdrop-blur-sm">
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
        {/* The file itself, never a link: into the phone's photos - a download in a browser -
          and to another app through the share sheet. */}
        <Round
          label={t(native ? 'media.save' : 'media.info.download')}
          icon={handOver.working === 'save' ? 'sync' : 'download'}
          spinning={handOver.working === 'save'}
          disabled={handOver.working !== null}
          onClick={handOver.save}
        />
        {handOver.shareable && (
          <Round
            label={t('media.share')}
            icon={handOver.working === 'share' ? 'sync' : 'ios_share'}
            spinning={handOver.working === 'share'}
            disabled={handOver.working !== null}
            onClick={handOver.share}
          />
        )}
      </div>
    </div>
  )
}

/** A hairline between two groups of buttons. */
function Line() {
  return <span aria-hidden="true" className="my-1 h-px w-5 shrink-0 bg-white/20" />
}

function Round({
  label,
  icon,
  count,
  filled = false,
  spinning = false,
  disabled = false,
  onClick,
}: {
  label: string
  icon: string
  count?: number | undefined
  filled?: boolean | undefined
  spinning?: boolean | undefined
  disabled?: boolean | undefined
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-busy={spinning || undefined}
      title={label}
      disabled={disabled}
      className="relative flex size-11 shrink-0 items-center justify-center rounded-full text-white transition hover:bg-white/15 disabled:opacity-60"
      onClick={onClick}
    >
      <Symbol name={icon} size={22} filled={filled} className={cn(spinning && 'animate-spin')} />
      {/* In a column there is no room beside the icon, so what there is of a thing is a small
        number on its shoulder. */}
      {count !== undefined && count > 0 && (
        <span className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-black/70 px-1 text-2xs tabular-nums leading-4">
          {count}
        </span>
      )}
    </button>
  )
}
