import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import type { Medium } from '@/features/albums/use-albums'
import { formatDuration } from '@/features/media/format'
import { downloadOriginal } from '@/features/media/original'
import { useMediumDetail } from '@/features/media/use-medium'
import { usePlayback } from '@/features/media/use-playback'
import { useMediaFaces } from '@/features/people/use-people'
import { REACTIONS } from '@/features/social/reactions'
import { useSocial, useToggleFavorite, useToggleLike } from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/** How long the chrome stays after the last sign of life. */
const REST_MS = 5000
/** What one step on the speed dial is, and where it starts over. */
const SPEED_STEP = 0.25
const SPEED_MAX = 2

interface ChromeProps {
  medium: Medium
  /** Where in the album this one stands, for the counter. */
  position: { index: number; total: number }
  onBack: () => void
  onComments: () => void
  onInfo: () => void
  onPrevious: () => void
  onNext: () => void
  /** Heart, star and the conversation only where a query client is. */
  social: boolean
  findVideo: () => HTMLVideoElement | null
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
  onPrevious,
  onNext,
  social,
  findVideo,
  actions,
  onSimilar,
}: ChromeProps) {
  const { t } = useTranslation()
  const [awake, setAwake] = useState(true)
  const [expanded, setExpanded] = useState(false)
  const [emojis, setEmojis] = useState(false)
  const sleep = useRef<number | undefined>(undefined)

  // Every sign of life puts the rest off; the chrome goes when nothing has happened for a while.
  useEffect(() => {
    const stir = () => {
      setAwake(true)
      window.clearTimeout(sleep.current)
      sleep.current = window.setTimeout(() => {
        setAwake(false)
        setEmojis(false)
      }, REST_MS)
    }
    stir()
    window.addEventListener('pointermove', stir)
    window.addEventListener('keydown', stir)
    return () => {
      window.clearTimeout(sleep.current)
      window.removeEventListener('pointermove', stir)
      window.removeEventListener('keydown', stir)
    }
  }, [medium.id])

  return (
    <div
      data-viewer-chrome
      className={cn(
        'pointer-events-none absolute inset-0 z-[1580] transition-opacity duration-300 motion-reduce:transition-none',
        awake ? 'opacity-100' : 'opacity-0',
      )}
      aria-hidden={!awake}
    >
      <Top
        position={position}
        onBack={onBack}
        actions={actions}
        title={medium.origin.filename}
      />

      {/* The way through the album, for a screen with a mouse. */}
      <Arrow side="left" label={t('media.previous')} onClick={onPrevious} />
      <Arrow side="right" label={t('media.next')} onClick={onNext} />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/55 to-transparent pb-[max(env(safe-area-inset-bottom),12px)] pt-10">
        <div className="pointer-events-auto mx-auto flex w-full max-w-[720px] flex-col gap-2 px-4">
          <p className="truncate font-mono text-xs-plus text-white/70">
            {medium.origin.filename}
          </p>
          <Summary
            mediaId={medium.id}
            expanded={expanded}
            onExpand={() => {
              setExpanded(true)
            }}
          />
          <Tags mediaId={medium.id} />
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
          <VideoBar medium={medium} findVideo={findVideo} />
        </div>
      </div>
    </div>
  )
}

function Top({
  position,
  onBack,
  actions,
  title,
}: {
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
        className="pointer-events-auto flex size-11 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/65"
        onClick={onBack}
      >
        <Symbol name="arrow_back" size={22} />
      </button>
      <span className="pointer-events-none rounded-full bg-black/40 px-3 py-1 text-xs-plus tabular-nums text-white/80">
        {position.index + 1} / {position.total}
      </span>
      <div className="pointer-events-auto flex size-11 items-center justify-center">{actions}</div>
    </div>
  )
}

function Arrow({
  side,
  label,
  onClick,
}: {
  side: 'left' | 'right'
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      className={cn(
        'pointer-events-auto absolute top-1/2 hidden size-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/35 text-white transition hover:bg-black/60 md:flex',
        side === 'left' ? 'left-3' : 'right-3',
      )}
      onClick={onClick}
    >
      <Symbol name={side === 'left' ? 'chevron_left' : 'chevron_right'} size={26} />
    </button>
  )
}

/** What the AI made of the picture, in one line until somebody wants the rest. */
function Summary({
  mediaId,
  expanded,
  onExpand,
}: {
  mediaId: string
  expanded: boolean
  onExpand: () => void
}) {
  const { t } = useTranslation()
  const detail = useMediumDetail(mediaId)
  const analysis = detail.data?.analysis
  const transcript = detail.data?.transcript
  const spoken = transcript?.parts.map((part) => part.text).join(' ')
  const said = [analysis?.caption, spoken].filter(Boolean).join(' · ')
  if (!said) return null

  return (
    <p className={cn('text-base text-white/90', expanded ? '' : 'line-clamp-2')}>
      {said}
      {!expanded && said.length > 90 && (
        <button
          type="button"
          className="ml-1 font-medium text-white underline-offset-2 hover:underline"
          onClick={onExpand}
        >
          {t('media.more')}
        </button>
      )}
    </p>
  )
}

/** Who is on the picture, as names one can read from across the room. */
function Tags({ mediaId }: { mediaId: string }) {
  const faces = useMediaFaces(mediaId)
  const named = (faces.data ?? []).filter((item) => item.person)
  if (named.length === 0) return null

  return (
    <ul className="flex flex-wrap gap-1.5">
      {named.map((item) => (
        <li
          key={item.face.id}
          className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs-plus text-white"
        >
          {item.person?.name}
        </li>
      ))}
    </ul>
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
    <div className="relative flex items-center justify-between gap-1 pt-1">
      {emojis && (
        <div className="absolute -top-12 left-0 flex gap-1 rounded-full bg-black/70 px-2 py-1.5 backdrop-blur-sm">
          {REACTIONS.map((reaction) => (
            <button
              key={reaction.key}
              type="button"
              aria-label={reaction.key}
              className="flex size-9 items-center justify-center rounded-full text-[20px] transition hover:bg-white/15"
              onClick={() => {
                like.mutate(reaction.key)
                onEmojis()
              }}
            >
              {reaction.emoji}
            </button>
          ))}
        </div>
      )}

      <Round label={t('comments.title')} icon="chat_bubble" count={state?.comments} onClick={onComments} />
      <Round
        label={t(state?.favorite ? 'walhall.remove' : 'walhall.keep')}
        icon="star"
        filled={state?.favorite}
        onClick={() => {
          favorite.mutate(!state?.favorite)
        }}
      />
      <Round
        label={t('social.like')}
        icon="favorite"
        filled={state?.liked}
        count={state?.likes}
        onClick={onEmojis}
      />
      <Round label={t('media.info.show')} icon="info" onClick={onInfo} />
      {onSimilar && (
        <Round label={t('media.similar')} icon="image_search" onClick={onSimilar} />
      )}
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
  )
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
      className="flex h-11 flex-1 items-center justify-center gap-1.5 rounded-full text-white transition hover:bg-white/15"
      onClick={onClick}
    >
      <Symbol name={icon} size={22} filled={filled} />
      {count !== undefined && count > 0 && (
        <span className="text-xs-plus tabular-nums">{count}</span>
      )}
    </button>
  )
}

/** Under the buttons for a video: where it stands, how fast it runs, whether it is heard. */
function VideoBar({
  medium,
  findVideo,
}: {
  medium: Medium
  findVideo: () => HTMLVideoElement | null
}) {
  const { t } = useTranslation()
  const playback = usePlayback(medium.kind === 'video' ? findVideo : undefined)
  if (medium.kind !== 'video' || !playback.attached) return null

  const total = medium.duration_seconds ?? 0
  const left = Math.max(0, Math.round(total - playback.time))

  return (
    <div className="flex items-center gap-3 border-t border-white/10 pt-2 text-white">
      <button
        type="button"
        aria-label={t(playback.playing ? 'media.pause' : 'media.play')}
        className="flex size-10 items-center justify-center rounded-full transition hover:bg-white/15"
        onClick={() => {
          const video = findVideo()
          if (!video) return
          if (video.paused) void video.play().catch(() => undefined)
          else video.pause()
        }}
      >
        <Symbol name={playback.playing ? 'pause' : 'play_arrow'} size={24} filled />
      </button>

      <span className="text-xs-plus tabular-nums text-white/80">-{formatDuration(left)}</span>

      <button
        type="button"
        aria-label={t('media.speed')}
        className="ml-auto rounded-full px-2.5 py-1 text-xs-plus tabular-nums transition hover:bg-white/15"
        onClick={() => {
          const video = findVideo()
          const next =
            playback.rate >= SPEED_MAX
              ? SPEED_STEP
              : Math.round((playback.rate + SPEED_STEP) * 100) / 100
          if (video) video.playbackRate = next
        }}
      >
        {playback.rate}&times;
      </button>

      <button
        type="button"
        aria-label={t(playback.muted ? 'media.unmute' : 'media.mute')}
        className="flex size-10 items-center justify-center rounded-full transition hover:bg-white/15"
        onClick={() => {
          const video = findVideo()
          if (!video) return
          video.muted = !video.muted
        }}
      >
        <Symbol name={playback.muted ? 'volume_off' : 'volume_up'} size={22} />
      </button>
    </div>
  )
}
