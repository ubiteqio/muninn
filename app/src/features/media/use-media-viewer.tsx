import 'photoswipe/style.css'

import PhotoSwipe from 'photoswipe'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { DialogContainer } from '@/components/ui/dialog'
import type { Medium } from '@/features/albums/use-albums'
import { MediaComments } from '@/features/media/media-comments'
import { DescribedMediaInfo } from '@/features/media/media-info'
import { MediaStagesMenu } from '@/features/media/media-stages'
import { STIRRED } from '@/features/media/stirred'
import { ViewerChrome } from '@/features/media/viewer-chrome'

/** What the viewer assumes when a medium never got its size read. */
const FALLBACK_WIDTH = 1600
const FALLBACK_HEIGHT = 1200

/** How often the video of a slide is looked for while PhotoSwipe is still building it. */
const LOOK_AGAIN_MS = 80
const LOOK_AT_MOST = 25

/**
 * What counts as a hand on the video, and so brings the buttons back.
 *
 * The tap first, for the browser that passes it on. Where it does not - a phone keeps the taps
 * that land on the media controls to itself - what the tap did is heard instead: a playback
 * started, stopped, wound on, or the sound turned up. One of the two always arrives.
 */
const TOUCHED_BY = ['pointerdown', 'click', 'play', 'pause', 'seeking', 'volumechange'] as const

interface ViewerAddress {
  /** The medium the address asks for, or nothing when the album itself is on screen. */
  current: string | undefined
  /** Put another medium into the address, or take it out again when the viewer closes. */
  onCurrentChange: (mediaId: string | undefined) => void
  /** Where a video starts, by medium id - a search hit starts where it matched. */
  startAt?: ReadonlyMap<string, number> | undefined
  /** Offered as "Ähnliche Bilder" in the viewer's head when given. */
  onSimilar?: ((mediaId: string) => void) | undefined
  /** Heart and star in the viewer's head. Asks the server, so only where a query client is. */
  social?: boolean | undefined
  /** Moves on by itself every this many milliseconds, until the last picture or a touch. */
  slideshow?: number | undefined
  /**
   * Asked for the next page when the end of the list comes into reach.
   *
   * An album hands the viewer the page it is showing. Without this, picture 100 of 4.000 is
   * the end of the world: the gallery turns round to picture 1, because that is what a gallery
   * does when it runs out. With it, the screen fetches the next page while the last pictures
   * are being looked at, and the viewer simply carries on into it.
   */
  onEndReached?: (() => void) | undefined
  /** Whether more can still arrive. While it can, the end is not the end and does not wrap. */
  hasMore?: boolean | undefined
}

/** How close to the end the next page is asked for: one picture is not enough warning. */
const ASK_WITHIN = 3

/** How long the hand has to rest before the address is told which picture it came to. */
const SETTLED_MS = 250

/**
 * Whether an open gallery has to be sent somewhere.
 *
 * Only a changed address moves it - a link, the back button, a picture named from elsewhere -
 * and only when it is not there already. What it must never answer to is its own move: between
 * a swipe and the navigation that follows, the address still names the picture before, and a
 * gallery sent back there is a gallery that cannot be moved at all.
 */
export function steers(
  current: string | undefined,
  seen: string | undefined,
  at: number,
  wanted: number,
): boolean {
  return current !== seen && at !== wanted
}

interface Viewer {
  /** Open the gallery at this position in the list it was built with. */
  open: (index: number) => void
  /** Belongs into the page: the info panel, rendered inside the open gallery. */
  panel: ReactNode
}

/**
 * Full screen with zoom and swipe, as the concept asks for.
 *
 * What opens is the large preview, not the original - that is the point of deriving them. The
 * original stays one address away for anybody who wants it.
 *
 * The address decides what is open, not a click: a picture can be linked to, the back button of
 * a phone closes the viewer instead of leaving the album, and reloading the page lands on the
 * same picture. A click only writes the medium into the address; the gallery follows.
 *
 * The info panel is React, not markup poked into the gallery: it shows dates, cameras and paths
 * that want translating and formatting. It goes into the gallery's own element through a portal,
 * so it sits above the picture and disappears with it.
 */
export function useMediaViewer(media: Medium[], address: ViewerAddress): Viewer {
  const {
    current,
    onCurrentChange,
    startAt,
    onSimilar,
    social = false,
    slideshow,
    onEndReached,
    hasMore = false,
  } = address
  const { t } = useTranslation()
  const [host, setHost] = useState<HTMLElement | null>(null)
  // The speech bubble opens the panel and takes it straight to the conversation.
  const [index, setIndex] = useState(0)
  // One panel at a time beside the picture: its details, or the conversation about it.
  const [sheet, setSheet] = useState<'info' | 'comments' | null>(null)
  const gallery = useRef<PhotoSwipe | null>(null)
  /** The screen is going away, taking the gallery with it. */
  const leaving = useRef(false)

  /**
   * Take the picture off the screen.
   *
   * Normally this is a fade out, after which PhotoSwipe says 'destroy' and the handler below
   * clears up. It refuses while it is still opening - a browser cannot turn a running transition
   * around - and then the element has to go by hand, or the picture would stay on screen with
   * the address saying otherwise.
   */
  const shut = useCallback(() => {
    const open = gallery.current
    if (open === null) return

    open.close()
    if (open.isDestroying) return

    open.element?.remove()
    gallery.current = null
    setHost(null)
    setSheet(null)
  }, [])

  /*
   * The callbacks as they are right now, without the gallery depending on their identity.
   *
   * A caller that writes its handler inline - most of them do - hands over a new function on
   * every render, and the effect below would then run again after every render. It would find
   * the gallery open and pull it to where the address says it is; but the address is set by a
   * navigation, which lands a moment after the picture has already moved, and the picture was
   * dragged back to the one before. Paging simply did not work, on any screen that keeps the
   * open medium in the address and passes a handler inline.
   */
  const latest = useRef(onCurrentChange)
  useEffect(() => {
    latest.current = onCurrentChange
  }, [onCurrentChange])

  /**
   * The medium the address named the last time this looked, so only a change of the address
   * moves the gallery. Not the medium the gallery moved to of its own accord: between a swipe
   * and the navigation that follows it, those two are different, and comparing against the
   * wrong one pulls the picture straight back to where it came from.
   */
  const seen = useRef<string | undefined>(undefined)

  const ask = useRef(onEndReached)
  useEffect(() => {
    ask.current = onEndReached
  }, [onEndReached])

  /*
   * The slides as they are now, which is not as they were when the gallery opened.
   *
   * PhotoSwipe is built once with what there was; a page that arrives afterwards would never be
   * seen. Its filters are asked every time it needs to know how many there are or what the next
   * one is, so a list that grows is enough - nothing has to be rebuilt, and the picture on
   * screen is not disturbed.
   */
  const slides = useRef(media.map((medium) => slideOf(medium, startAt?.get(medium.id))))
  /** The media behind those slides, for everything that answers a move to another picture. */
  const listed = useRef(media)
  useEffect(() => {
    slides.current = media.map((medium) => slideOf(medium, startAt?.get(medium.id)))
    listed.current = media
    if (gallery.current === null) return

    // What it was built with, as it is now: the filters below answer from the same array, and
    // anything that reads the source directly must not see the list the gallery opened on.
    gallery.current.options.dataSource = slides.current
    // The end is only the end when nothing more can come; until then it must not turn round.
    gallery.current.options.loop = !hasMore
    // Still near the end after a page arrived: somebody is going through faster than the pages
    // come, so the one after it is asked for straight away.
    if (gallery.current.currIndex >= media.length - ASK_WITHIN) onEndReached?.()
  }, [media, startAt, hasMore, onEndReached])

  useEffect(() => {
    const wanted = current === undefined ? -1 : media.findIndex((item) => item.id === current)

    if (wanted < 0) {
      shut()
      return
    }

    if (gallery.current) {
      /*
       * Only when the address itself changed - a link, the back button - and only when the
       * gallery is somewhere else.
       *
       * This effect runs again whenever the list is replaced, and on a screen that reads the
       * library while somebody browses it, that happens every couple of seconds. The address
       * follows a move by a navigation, which lands a moment after the picture has already
       * turned; a list replaced in that moment used to pull the gallery back to where the
       * address still pointed, and the key press looked as if it had done nothing at all.
       */
      if (steers(current, seen.current, gallery.current.currIndex, wanted)) {
        gallery.current.goTo(wanted)
      }
      seen.current = current
      return
    }
    seen.current = current

    // Built from the list as it is in this very render: the ref is kept up to date by the
    // effect above, but a gallery must never be able to open on yesterday's pictures.
    slides.current = media.map((medium) => slideOf(medium, startAt?.get(medium.id)))
    listed.current = media

    const opened = new PhotoSwipe({
      dataSource: slides.current,
      index: wanted,
      // While a next page can still arrive, the last picture is not the last picture: turning
      // round to the first there is what made picture 100 of 4.000 lead back to picture 1.
      loop: !hasMore,
      // Fully opaque: the light page would otherwise show through, header and all.
      bgOpacity: 1,
      // Its own buttons, counter and arrows stay off: what lies over the picture is ours, and
      // it rests when nobody moves. A tap on a picture still zooms - that is PhotoSwipe's.
      zoom: false,
      close: false,
      counter: false,
      arrowPrev: false,
      arrowNext: false,
      // A click on a picture zooms it, where there is a mouse. A finger pinches, or taps twice;
      // its single tap belongs to the chrome, which it brings back when that has rested.
      imageClickAction: 'zoom',
      tapAction: false,
      doubleTapAction: 'zoom',
    })

    // What it was built with is a snapshot; these two are asked every time it needs to know how
    // long the list is and what stands at a position, so a page that arrives later is simply
    // there - no rebuild, no flicker, and the picture on screen never moves.
    opened.addFilter('numItems', () => slides.current.length)
    opened.addFilter('itemData', (itemData, position) => slides.current[position] ?? itemData)

    /*
     * The address follows when the hand comes to rest, not at every picture it passes.
     *
     * Writing it is a navigation, and a navigation renders the whole screen behind the gallery
     * - the tree, the grid, the pager, the pills. Holding the arrow key down through an album
     * then means one of those per picture, and the pictures arrive in fits and starts. What is
     * on screen is the gallery's own business; the address only has to be right for a link, a
     * reload and the back button, and a quarter of a second later is soon enough for all three.
     */
    let saying: ReturnType<typeof setTimeout> | undefined
    const sayLater = (mediaId: string | undefined) => {
      clearTimeout(saying)
      saying = setTimeout(() => {
        latest.current(mediaId)
      }, SETTLED_MS)
    }
    opened.on('destroy', () => {
      clearTimeout(saying)
    })

    /** Near the end: time to ask for the next page, while there are still pictures to look at. */
    const askIfNearTheEnd = () => {
      if (opened.currIndex >= slides.current.length - ASK_WITHIN) ask.current?.()
    }

    // Typing is not steering: a "z" in a name or a comment is a letter, not zoom, and the arrows
    // move the cursor. Escape in a dialog closes the dialog, not the viewer behind it.
    opened.on('keydown', (event) => {
      const target = event.originalEvent.target
      if (!(target instanceof Element)) return
      // The viewer is a dialog itself; only one opened over it counts.
      const dialog = target.closest('[role="dialog"]')
      if (
        target.closest('input, textarea, [contenteditable]') ||
        (dialog !== null && dialog !== opened.element)
      ) {
        event.preventDefault()
      }
    })
    // A video one opened is a video one wants to see: it starts by itself.
    //
    // PhotoSwipe builds the slide a moment after the tap, so the element is looked for a few
    // times rather than once. And the browser may refuse to play - by then the play no longer
    // answers the tap - so it is then played without sound, which is always allowed, with the
    // controls right there to turn it on.
    let waiting: ReturnType<typeof setTimeout> | undefined
    const playShown = (tries = 0) => {
      clearTimeout(waiting)
      const video = opened.currSlide?.container.querySelector('video')
      if (!video) {
        if (tries < LOOK_AT_MOST)
          waiting = setTimeout(() => {
            playShown(tries + 1)
          }, LOOK_AGAIN_MS)
        return
      }
      void video.play().catch(() => {
        video.muted = true
        void video.play().catch(() => undefined)
      })
    }

    opened.on('change', () => {
      setIndex(opened.currIndex)
      // The list as it is now, not as it was when this opened: a picture from a page that
      // arrived since is a picture the address must be able to name, or the viewer would be
      // told that what it is showing does not exist and close itself.
      const moved = listed.current[opened.currIndex]?.id
      sayLater(moved)
      askIfNearTheEnd()
      // PhotoSwipe keeps the neighbouring slides in the DOM, so a video that is left behind
      // plays on - out of sight and, worse, still audible. Only the slide on screen may play.
      const shown = opened.currSlide?.container
      for (const video of opened.element?.querySelectorAll('video') ?? []) {
        if (!shown?.contains(video)) video.pause()
      }
      playShown()
    })
    /*
     * The slide the viewer opens on, and every one built while it is open.
     *
     * Nothing here answers a tap on the video: the element carries `controls`, so the browser
     * draws play, pause and the scrubber and answers them itself. A listener of ours that
     * toggled the playback would undo what the button had just done.
     *
     * What it does do is notice that the video was touched at all - the tap itself where the
     * page is told about it, and otherwise what came of it, a play or a pause or a seek. Only
     * the buttons are brought back by this; the video is left to do what it was asked.
     */
    opened.on('contentActivate', ({ content }) => {
      playShown()
      const video = content.element?.querySelector('video')
      if (!video) return
      const touched = () => {
        window.dispatchEvent(new Event(STIRRED))
      }
      for (const name of TOUCHED_BY) video.addEventListener(name, touched)
    })
    // The slide one leaves: its content goes, but a video that was playing carries on - taken
    // out of the page it keeps its sound. This is the moment to stop it.
    opened.on('contentDeactivate', ({ content }) => {
      content.element?.querySelectorAll('video').forEach((video) => {
        video.pause()
      })
    })
    opened.on('destroy', () => {
      clearTimeout(waiting)
      gallery.current = null
      setHost(null)
      setSheet(null)
      if (!leaving.current) latest.current(undefined)
    })

    if (slideshow !== undefined) {
      // A slideshow runs to the last picture; a touch, a click or a key hands over to the hand.
      const timer = window.setInterval(() => {
        // The list it runs to the end of is the list as it is now, pages and all.
        if (opened.currIndex >= slides.current.length - 1) window.clearInterval(timer)
        else opened.next()
      }, slideshow)
      const stop = () => {
        window.clearInterval(timer)
      }
      opened.on('pointerDown', stop)
      opened.on('keydown', stop)
      opened.on('destroy', stop)
    }

    // A video is laid out at the size it is handed - PhotoSwipe scales pictures, not markup -
    // so a phone that is turned would leave it in the shape of the orientation it was opened
    // in. Before every new measurement the video slides are handed the screen as it is now.
    const measure = () => {
      for (const slide of slides.current) {
        if ('html' in slide) {
          slide.width = window.innerWidth
          slide.height = window.innerHeight
        }
      }
    }
    opened.on('beforeResize', measure)

    /*
     * Turning a phone is not an ordinary resize. iOS still reports the old screen while the
     * rotation is running, so measuring when it says so measures what was there before. It is
     * measured again once the turn has settled - after two frames, and once more a beat later
     * for the browser whose bars are still sliding into place - and PhotoSwipe is made to lay
     * everything out again with what it now knows.
     */
    const settled = () => {
      measure()
      fitToScreen(opened)
    }
    let again = 0
    const turned = () => {
      window.clearTimeout(again)
      requestAnimationFrame(() => {
        requestAnimationFrame(settled)
      })
      again = window.setTimeout(settled, 300)
    }
    window.addEventListener('orientationchange', turned)
    window.visualViewport?.addEventListener('resize', turned)
    opened.on('destroy', () => {
      window.clearTimeout(again)
      window.removeEventListener('orientationchange', turned)
      window.visualViewport?.removeEventListener('resize', turned)
    })

    setIndex(wanted)
    opened.init()
    // Opened on the last picture of a page - which is exactly how somebody reaches the end -
    // the next one has to be asked for now, not at the first swipe that finds nothing.
    askIfNearTheEnd()
    // PhotoSwipe cancels every turn of the wheel inside it, to pan and zoom the picture. Over
    // the info panel and dialogs that means no scrolling at all: there the wheel goes past it.
    opened.element?.addEventListener(
      'wheel',
      (event) => {
        const target = event.target
        if (target instanceof Element && !target.closest('.pswp__scroll-wrap')) {
          event.stopPropagation()
        }
      },
      { capture: true, passive: true },
    )
    gallery.current = opened
    setHost(opened.element ?? null)
  }, [current, media, shut, slideshow, startAt, t])

  // Leaving the album while the gallery is open would otherwise leave it hanging over the next
  // screen: it lives in the body, not in this component's markup. Its closing is then not news
  // for the address: the next screen already has it, and "closed" would lead back here.
  useEffect(() => {
    leaving.current = false
    return () => {
      leaving.current = true
      shut()
    }
  }, [shut])

  const open = useCallback(
    (position: number) => {
      const medium = media[position]
      if (medium) onCurrentChange(medium.id)
    },
    [media, onCurrentChange],
  )

  // The video of the slide on screen; PhotoSwipe keeps its neighbours loaded as well.
  const findVideo = useCallback(
    () => gallery.current?.currSlide?.container.querySelector('video') ?? null,
    [],
  )

  // A tap anywhere beside the open panel closes it - on the picture, the arrows, the buttons -
  // and does nothing else: a tap on the background would otherwise close the whole viewer, one
  // on an arrow turn to the next picture. Not a tap inside the panel, in a dialog or menu it
  // opened, or on the button that toggles it: those answer their own taps.
  useEffect(() => {
    if (host === null || sheet === null) return
    const swallow = (event: Event) => {
      event.stopPropagation()
      event.preventDefault()
    }
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Element)) return
      if (
        target.closest(
          '[data-viewer-panel], [data-viewer-toggle], [data-viewer-chrome], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]',
        )
      ) {
        return
      }
      // The viewer is a dialog itself; only a dialog opened on top of it keeps the panel.
      const dialog = target.closest('[role="dialog"]')
      if (dialog !== null && dialog !== host) return
      setSheet(null)
      // PhotoSwipe reads taps from the pointer events, buttons from the click that follows.
      swallow(event)
      host.addEventListener('pointerup', swallow, { capture: true, once: true })
      host.addEventListener('click', swallow, { capture: true, once: true })
      window.setTimeout(() => {
        host.removeEventListener('pointerup', swallow, { capture: true })
        host.removeEventListener('click', swallow, { capture: true })
      }, 600)
    }
    host.addEventListener('pointerdown', onPointerDown, true)
    return () => {
      host.removeEventListener('pointerdown', onPointerDown, true)
    }
  }, [host, sheet])

  const shown = media[index]
  const close = () => {
    setSheet(null)
  }
  const panel =
    host === null || sheet === null || shown === undefined
      ? null
      : createPortal(
          <DialogContainer.Provider value={host}>
            {sheet === 'info' ? (
              <DescribedMediaInfo
                // A new medium starts a new panel, so no description of the last one lingers.
                key={shown.id}
                medium={shown}
                findVideo={shown.kind === 'video' ? findVideo : undefined}
                onClose={close}
              />
            ) : (
              <MediaComments key={shown.id} medium={shown} onClose={close} />
            )}
          </DialogContainer.Provider>,
          host,
        )

  const chrome =
    host === null || shown === undefined
      ? null
      : createPortal(
          <ViewerChrome
            key={shown.id}
            medium={shown}
            position={{ index, total: media.length }}
            social={social}
            busy={sheet !== null}
            onBack={() => {
              onCurrentChange(undefined)
            }}
            onComments={() => {
              setSheet((open) => (open === 'comments' ? null : 'comments'))
            }}
            onInfo={() => {
              setSheet((open) => (open === 'info' ? null : 'info'))
            }}
            actions={
              <DialogContainer.Provider value={host}>
                <MediaStagesMenu
                  mediaId={shown.id}
                  filename={shown.origin.filename}
                  onWithdrawn={() => {
                    // Nothing left to look at: the viewer closes on the album behind it.
                    onCurrentChange(undefined)
                  }}
                />
              </DialogContainer.Provider>
            }
            {...(onSimilar
              ? {
                  onSimilar: () => {
                    onSimilar(shown.id)
                  },
                }
              : {})}
          />,
          host,
        )

  return {
    open,
    panel: (
      <>
        {panel}
        {chrome}
      </>
    ),
  }
}

function slideOf(medium: Medium, startAt?: number) {
  const width = medium.width ?? FALLBACK_WIDTH
  const height = medium.height ?? FALLBACK_HEIGHT

  if (medium.kind === 'video' && medium.urls.video) {
    // A media fragment: the browser starts the video at that second, no script needed.
    const source =
      startAt === undefined ? medium.urls.video : `${medium.urls.video}#t=${String(startAt)}`
    // A picture is scaled to fill the screen; a video is not - PhotoSwipe lays out its own
    // markup at the size it is given and leaves it there. Given the video's own size, a
    // portrait clip filmed on a phone sat as a small rectangle in the middle of a black
    // screen. The slide is the screen, and the video fits itself into it.
    return {
      html: videoMarkup(source, medium.urls.poster),
      width: window.innerWidth,
      height: window.innerHeight,
    }
  }

  return { src: medium.urls.preview ?? medium.urls.original, width, height, alt: '' }
}

/**
 * Hand the video on screen the screen as it is now, and lay it out again.
 *
 * What a slide works its size out from is taken once, when it is built, so writing the new size
 * into its data alone never reaches the layout - both have to be told. Exported so the test
 * that measures a video at two orientations drives the same code the app does.
 */
export function fitToScreen(opened: PhotoSwipe): void {
  const slide = opened.currSlide
  if (slide && 'html' in slide.data) {
    slide.data.width = window.innerWidth
    slide.data.height = window.innerHeight
    slide.width = window.innerWidth
    slide.height = window.innerHeight
  }
  opened.updateSize(true)
}

export function videoMarkup(source: string, poster: string | null): string {
  const attributes = [
    'controls',
    'playsinline',
    'style="width:100%;height:100%;object-fit:contain"',
    `src="${escapeAttribute(source)}"`,
    poster ? `poster="${escapeAttribute(poster)}"` : '',
  ]
  // The whole slide, edge to edge. Our own buttons stand in a column down the right-hand side
  // now, so nothing of ours is along the bottom for the browser's controls to meet, and no
  // strip of the screen has to be kept clear of the picture.
  //
  // Pinned to the slide rather than told to be all of it: a height given as a percentage needs
  // every parent above it to have one, and the slide's does not come from the stylesheet.
  const box = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center'
  return `<div style="${box}"><video ${attributes.join(' ')}></video></div>`
}

/** The addresses come from our own API, but building markup without escaping is a bad habit. */
function escapeAttribute(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;')
}
