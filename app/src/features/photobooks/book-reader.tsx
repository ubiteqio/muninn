import '@/features/photobooks/book.css'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { BookPage, type Side } from '@/features/photobooks/book-page'
import type { Leaf } from '@/features/photobooks/use-photobooks'

/** Below this the book shows one page; above it, two, as a book lies open. */
const SPREAD_FROM = 900

/** A swipe shorter than this is somebody holding the phone, not turning a page. */
const SWIPE = 60

/**
 * A photo book, full screen.
 *
 * Nothing of the app is on screen while it is open: no rail, no header, no bell. A book is read,
 * not operated, so what is left is the fewest possible ways to turn a page - arrow keys, a
 * swipe, and a small bar on a desktop - and Escape, which closes it and hands the reader back
 * to the shelf.
 */
export function BookReader({
  pages,
  title,
  onLeave,
}: {
  pages: Leaf[]
  title: string
  onLeave: () => void
}) {
  const { t } = useTranslation()
  const [at, setAt] = useState(0)
  const [spread, setSpread] = useState(() => howMany())
  const [printing, setPrinting] = useState(false)
  const from = useRef<number | null>(null)

  useEffect(() => {
    const measure = () => {
      setSpread(howMany())
    }
    addEventListener('resize', measure)
    return () => {
      removeEventListener('resize', measure)
    }
  }, [])

  const step = useCallback(
    (by: number) => {
      setAt((was) => {
        const next = was + by * spread
        // A spread always opens on an even page, so the fold stays where it was.
        const settled = spread === 2 && next % 2 === 1 ? next - 1 : next
        return Math.max(0, Math.min(settled, pages.length - 1))
      })
    },
    [pages.length, spread],
  )

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onLeave()
        return
      }
      if (event.key === 'ArrowRight' || event.key === ' ') {
        event.preventDefault()
        step(1)
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        step(-1)
      }
    }
    addEventListener('keydown', onKey)
    return () => {
      removeEventListener('keydown', onKey)
    }
  }, [onLeave, step])

  /**
   * Printing hands the printer the whole book rather than the two pages on screen: a printer has
   * no arrow keys. The pages go back afterwards, whether the print was made or called off.
   */
  const print = useCallback(() => {
    setPrinting(true)
    const done = () => {
      setPrinting(false)
    }
    addEventListener('afterprint', done, { once: true })
    // One frame, so the browser has the whole book in the document before it measures it.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.print()
      })
    })
  }, [])

  const onTouchStart = (event: React.TouchEvent) => {
    from.current = event.touches[0]?.clientX ?? null
  }

  const onTouchEnd = (event: React.TouchEvent) => {
    const to = event.changedTouches[0]?.clientX ?? null
    if (from.current !== null && to !== null) {
      if (from.current - to > SWIPE) step(1)
      if (to - from.current > SWIPE) step(-1)
    }
    from.current = null
  }

  const open = printing ? pages : pages.slice(at, at + spread)
  const firstShown = printing ? 0 : at

  return (
    <div className="book" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      {open.map((page, index) => (
        <BookPage
          key={`${firstShown + index}`}
          page={page}
          number={firstShown + index + 1}
          side={sideOf(printing ? 1 : spread, index)}
        />
      ))}

      <button
        type="button"
        onClick={onLeave}
        aria-label={t('photobooks.close')}
        className="book-leave fixed top-4 right-4 z-10 flex size-10 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur"
      >
        <Symbol name="close" size={22} />
      </button>

      <nav className="book-bar" aria-label={title}>
        <button type="button" onClick={() => { step(-1); }} disabled={at === 0} aria-label={t('photobooks.back')}>
          ←
        </button>
        <span>
          {at + 1}
          {spread === 2 && at + 1 < pages.length ? `–${Math.min(at + spread, pages.length)}` : ''}
          {' / '}
          {pages.length}
        </span>
        <button
          type="button"
          onClick={() => { step(1); }}
          disabled={at + spread >= pages.length}
          aria-label={t('photobooks.on')}
        >
          →
        </button>
        <button type="button" onClick={print} aria-label={t('photobooks.print')}>
          <Symbol name="print" size={18} />
        </button>
      </nav>
    </div>
  )
}

function howMany(): number {
  return typeof window !== 'undefined' && window.innerWidth >= SPREAD_FROM ? 2 : 1
}

/**
 * Which side of the fold a page is on - and that follows from where it sits in what is on
 * screen, never from its number. A page numbered "right" while only one is shown was hidden by
 * the stylesheet, which is how every second page once came up black on a phone.
 */
export function sideOf(spread: number, index: number): Side {
  if (spread === 1) return 'single'
  return index === 0 ? 'left' : 'right'
}
