import { type KeyboardEvent, type MouseEvent, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import type { components } from '@/api/generated/schema'
import { formatDuration } from '@/features/media/format'
import { momentAt, spokenAt } from '@/features/media/story'
import { usePlayback } from '@/features/media/use-playback'
import { cn } from '@/lib/utils'

type Moment = components['schemas']['MomentView']
type Transcript = components['schemas']['TranscriptView']
type Spoken = components['schemas']['SpokenView']

interface VideoStoryProps {
  duration: number
  moments: Moment[]
  transcript: Transcript | null | undefined
  /** The video element on screen, found through the gallery. */
  findVideo?: (() => HTMLVideoElement | null) | undefined
}

/** How far the arrow keys move along the strip. */
const STEP_SECONDS = 5

/**
 * What happens in a video, following along while it plays.
 *
 * The summary above says what the video is about. This says what is on screen right now and
 * what is being said: one line for the picture, one for the words, both changing with the
 * playback. The strip underneath shows the whole length at a glance - where the picture was
 * looked at, where somebody speaks - and takes a tap to jump there. Everything that was said
 * waits folded away; nothing here is a wall of text unless asked for.
 */
export function VideoStory({ duration, moments, transcript, findVideo }: VideoStoryProps) {
  const { t } = useTranslation()
  const playback = usePlayback(findVideo)
  const parts = transcript?.parts ?? []
  const length = Math.max(duration, moments.at(-1)?.second ?? 0, parts.at(-1)?.end ?? 0, 1)

  const moment = momentAt(moments, playback.time)
  const spoken = spokenAt(parts, playback.time)

  if (moments.length === 0 && transcript === undefined) return null

  return (
    <section aria-label={t('media.story.title')} className="mt-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs-plus text-muted-foreground">{t('media.story.title')}</h3>
        <span className="font-mono text-xs-plus text-muted-foreground">
          {clock(playback.time)} / {clock(length)}
        </span>
      </div>

      <Strip
        length={length}
        moments={moments}
        parts={parts}
        time={playback.time}
        onSeek={playback.attached ? playback.seek : undefined}
      />

      {/* One line for the picture, one for the words: what is on screen right now. */}
      <div aria-live="polite" className="mt-3 space-y-2 rounded-lg bg-muted/40 p-3">
        {moment && (
          <p className="text-base text-foreground">
            <span className="mr-1.5 font-mono text-xs-plus text-accent">
              {clock(moment.second)}
            </span>
            {moment.caption}
          </p>
        )}
        {spoken && (
          <blockquote className="border-l-2 border-accent/60 pl-2.5 text-base italic text-foreground">
            „{spoken.text}“
          </blockquote>
        )}
        {!moment && !spoken && (
          <p className="text-xs-plus text-muted-foreground">{t('media.story.nothingYet')}</p>
        )}
      </div>

      {transcript && parts.length === 0 && (
        <p className="mt-2 text-xs-plus text-muted-foreground">{t('media.story.silent')}</p>
      )}

      {parts.length > 0 && (
        <Said
          parts={parts}
          current={spoken}
          onSeek={playback.attached ? playback.seek : undefined}
        />
      )}
    </section>
  )
}

/**
 * The whole video as a strip: the picture above, the words below, a line where it stands now.
 * A tap or the arrow keys move the video; it is a slider for anyone who cannot see it.
 */
function Strip({
  length,
  moments,
  parts,
  time,
  onSeek,
}: {
  length: number
  moments: Moment[]
  parts: Spoken[]
  time: number
  onSeek: ((seconds: number) => void) | undefined
}) {
  const { t } = useTranslation()
  const at = (seconds: number) => `${String(Math.min(100, (seconds / length) * 100))}%`

  const jump = (event: MouseEvent<HTMLDivElement>) => {
    if (!onSeek) return
    const box = event.currentTarget.getBoundingClientRect()
    if (box.width === 0) return
    onSeek(((event.clientX - box.left) / box.width) * length)
  }
  const step = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onSeek) return
    if (event.key === 'ArrowRight') onSeek(Math.min(length, time + STEP_SECONDS))
    else if (event.key === 'ArrowLeft') onSeek(Math.max(0, time - STEP_SECONDS))
    else return
    event.preventDefault()
  }

  return (
    <div
      role="slider"
      tabIndex={onSeek ? 0 : -1}
      aria-label={t('media.story.strip')}
      aria-valuemin={0}
      aria-valuemax={Math.round(length)}
      aria-valuenow={Math.round(time)}
      aria-valuetext={clock(time)}
      onClick={jump}
      onKeyDown={step}
      className={cn('relative mt-2 h-9 select-none', onSeek && 'cursor-pointer')}
    >
      {/* The picture: a fine line for every second that was looked at. */}
      <div className="absolute inset-x-0 top-0 h-4 overflow-hidden rounded-sm bg-muted/60">
        {moments.map((item) => (
          <span
            key={item.second}
            className="absolute inset-y-0 w-px bg-foreground/35"
            style={{ left: at(item.second) }}
          />
        ))}
      </div>
      {/* The words: a bar wherever somebody speaks. */}
      <div className="absolute inset-x-0 bottom-0 h-2.5 overflow-hidden rounded-sm bg-muted/40">
        {parts.map((part) => (
          <span
            key={`${String(part.start)}-${part.text}`}
            className="absolute inset-y-0 rounded-sm bg-accent/70"
            style={{
              left: at(part.start),
              width: `max(3px, ${String(((part.end - part.start) / length) * 100)}%)`,
            }}
          />
        ))}
      </div>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -inset-y-0.5 w-0.5 rounded-full bg-accent transition-[left] duration-200 ease-linear motion-reduce:transition-none"
        style={{ left: at(time) }}
      />
    </div>
  )
}

/** Everything that was said, folded away. Open, it follows the video and jumps on a tap. */
function Said({
  parts,
  current,
  onSeek,
}: {
  parts: Spoken[]
  current: Spoken | undefined
  onSeek: ((seconds: number) => void) | undefined
}) {
  const { t } = useTranslation()
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    // Keep the sentence being said in view, without pulling the whole page along.
    const shown = list.current?.querySelector<HTMLElement>('[aria-current="true"]')
    shown?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [current])

  return (
    <details className="group mt-3">
      <summary className="cursor-pointer list-none text-xs-plus text-muted-foreground hover:text-foreground">
        {t('media.story.said', { count: parts.length })}
        <span
          aria-hidden="true"
          className="ml-1 inline-block transition-transform group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <ol ref={list} className="mt-2 max-h-56 space-y-1 overflow-y-auto pr-1">
        {parts.map((part) => {
          const now = part === current
          return (
            <li key={`${String(part.start)}-${part.text}`}>
              <button
                type="button"
                aria-current={now}
                disabled={!onSeek}
                onClick={() => onSeek?.(part.start)}
                className={cn(
                  'flex w-full gap-2 rounded px-1.5 py-1 text-left text-base',
                  now ? 'bg-accent/15 text-foreground' : 'text-muted-foreground hover:bg-muted/50',
                )}
              >
                <span className="shrink-0 font-mono text-xs-plus leading-6">
                  {clock(part.start)}
                </span>
                <span>{part.text}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </details>
  )
}

function clock(seconds: number): string {
  return formatDuration(Math.floor(seconds)) || '0:00'
}
