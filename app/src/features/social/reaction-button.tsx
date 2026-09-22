import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { emojiOf, type Reaction, REACTIONS } from '@/features/social/reactions'
import type { Social } from '@/features/social/use-social'
import { cn } from '@/lib/utils'

/** Holding this long opens the reactions instead of giving a heart. */
const HOLD_MS = 450
/** Resting the pointer this long over the button opens them on a desktop. */
const HOVER_MS = 600

/**
 * The heart of the viewer, grown into reactions the way messengers do it: a tap gives a heart
 * (or takes one's own reaction back), holding - or resting the mouse on it, or a right click -
 * opens a row of eight to pick from. One's own reaction shows in the button.
 */
export function ReactionButton({
  state,
  pending,
  onReact,
}: {
  state: Social | undefined
  pending: boolean
  /** A reaction's name, or null to take one's own back. */
  onReact: (reaction: Reaction | null) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const hold = useRef<number | undefined>(undefined)
  const hover = useRef<number | undefined>(undefined)
  const held = useRef(false)
  const root = useRef<HTMLSpanElement>(null)
  const mine = state?.reaction ?? null

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', close, true)
    document.addEventListener('keydown', escape, true)
    return () => {
      document.removeEventListener('pointerdown', close, true)
      document.removeEventListener('keydown', escape, true)
    }
  }, [open])

  useEffect(
    () => () => {
      window.clearTimeout(hold.current)
      window.clearTimeout(hover.current)
    },
    [],
  )

  const pick = (reaction: Reaction) => {
    setOpen(false)
    onReact(reaction === mine ? null : reaction)
  }

  return (
    <span
      ref={root}
      className="flex flex-col items-center gap-0.5"
      onPointerEnter={(event) => {
        if (event.pointerType !== 'mouse') return
        hover.current = window.setTimeout(() => {
          setOpen(true)
        }, HOVER_MS)
      }}
      onPointerLeave={() => {
        window.clearTimeout(hover.current)
      }}
    >
      <span className="relative block">
        {open && (
          <div
            role="menu"
            aria-label={t('social.reactions')}
            // Above the heart, flush with its right edge: the rail sits at the right of the screen, so
            // the row grows into the picture, never off it.
            className="absolute bottom-[calc(100%+8px)] right-0 z-10 flex origin-bottom-right items-center gap-0.5 rounded-full bg-black/75 px-1.5 py-1 shadow-2xl ring-1 ring-white/15 backdrop-blur-md motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-95"
          >
            {REACTIONS.map((reaction) => (
              <button
                key={reaction.key}
                type="button"
                role="menuitemradio"
                aria-checked={reaction.key === mine}
                aria-label={t('social.reactWith', { emoji: reaction.emoji })}
                className={cn(
                  'grid size-9 place-items-center rounded-full text-[22px] leading-none transition hover:-translate-y-1 hover:scale-125 motion-reduce:hover:transform-none sm:size-10 sm:text-[24px]',
                  reaction.key === mine && 'bg-white/20',
                )}
                onClick={() => {
                  pick(reaction.key)
                }}
              >
                {reaction.emoji}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          aria-label={mine ? t('social.unlike') : t('social.like')}
          aria-haspopup="menu"
          aria-expanded={open}
          title={t('social.react')}
          aria-pressed={mine !== null}
          disabled={!state || pending}
          className="flex h-11 w-11 select-none items-center justify-center rounded-full bg-black/40 text-white ring-1 ring-white/15 backdrop-blur-md transition [-webkit-touch-callout:none] hover:bg-black/55 active:scale-95 disabled:opacity-60"
          onPointerDown={(event) => {
            if (event.button !== 0) return
            held.current = false
            hold.current = window.setTimeout(() => {
              held.current = true
              setOpen(true)
            }, HOLD_MS)
          }}
          onPointerUp={() => {
            window.clearTimeout(hold.current)
          }}
          onPointerCancel={() => {
            window.clearTimeout(hold.current)
          }}
          onContextMenu={(event) => {
            event.preventDefault()
            window.clearTimeout(hold.current)
            setOpen(true)
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
              event.preventDefault()
              setOpen(true)
            }
          }}
          onClick={() => {
            // The end of a long press is no tap.
            if (held.current) {
              held.current = false
              return
            }
            window.clearTimeout(hover.current)
            setOpen(false)
            onReact(mine ? null : 'heart')
          }}
        >
          {mine ? (
            <span aria-hidden="true" className="text-[22px] leading-none">
              {emojiOf(mine)}
            </span>
          ) : (
            <Symbol name="favorite" size={24} />
          )}
        </button>
      </span>
      <span
        aria-hidden="true"
        className="flex min-h-[14px] items-center gap-0.5 text-2xs font-medium tabular-nums text-white drop-shadow"
      >
        {state && state.likes > 0 && (
          <>
            <span className="text-[11px] leading-none">
              {state.reactions
                .slice(0, 2)
                .map((entry) => emojiOf(entry.reaction))
                .join('')}
            </span>
            <span>{state.likes}</span>
          </>
        )}
      </span>
    </span>
  )
}
