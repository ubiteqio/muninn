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
import { ViewerChrome } from '@/features/media/viewer-chrome'

/** What the viewer assumes when a medium never got its size read. */
const FALLBACK_WIDTH = 1600
const FALLBACK_HEIGHT = 1200

/** How often the video of a slide is looked for while PhotoSwipe is still building it. */
const LOOK_AGAIN_MS = 80
const LOOK_AT_MOST = 25

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
  const { current, onCurrentChange, startAt, onSimilar, social = false, slideshow } = address
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

  useEffect(() => {
    const wanted = current === undefined ? -1 : media.findIndex((item) => item.id === current)

    if (wanted < 0) {
      shut()
      return
    }

    if (gallery.current) {
      gallery.current.goTo(wanted)
      return
    }

    const slides = media.map((medium) => slideOf(medium, startAt?.get(medium.id)))
    const opened = new PhotoSwipe({
      dataSource: slides,
      index: wanted,
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
      onCurrentChange(media[opened.currIndex]?.id)
      // PhotoSwipe keeps the neighbouring slides in the DOM, so a video that is left behind
      // plays on - out of sight and, worse, still audible. Only the slide on screen may play.
      const shown = opened.currSlide?.container
      for (const video of opened.element?.querySelectorAll('video') ?? []) {
        if (!shown?.contains(video)) video.pause()
      }
      playShown()
    })
    // The slide the viewer opens on, and every one built while it is open.
    opened.on('contentActivate', ({ content }) => {
      playShown()
      // A tap on a picture zooms, which PhotoSwipe does itself; a tap on a video is what one
      // means by tapping a video. Its own controls keep their taps.
      const video = content.element?.querySelector('video')
      video?.addEventListener('click', (event) => {
        event.stopPropagation()
        if (video.paused) void video.play().catch(() => undefined)
        else video.pause()
      })
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
      if (!leaving.current) onCurrentChange(undefined)
    })

    if (slideshow !== undefined) {
      // A slideshow runs to the last picture; a touch, a click or a key hands over to the hand.
      const timer = window.setInterval(() => {
        if (opened.currIndex >= media.length - 1) window.clearInterval(timer)
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
      for (const slide of slides) {
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
  }, [current, media, onCurrentChange, onSimilar, shut, slideshow, social, startAt, t])

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
                <MediaStagesMenu mediaId={shown.id} />
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
  // The browser draws its controls along the bottom edge of the video, and our own buttons sit
  // along the bottom of the screen. A strip the height of ours is kept clear, so the video ends
  // above them and the two never meet. On most clips that strip is letterbox black anyway.
  //
  // Pinned to the slide rather than told to be all of it: a height given as a percentage needs
  // every parent above it to have one, and the slide's does not come from the stylesheet.
  const box =
    'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
    'padding-bottom:calc(max(env(safe-area-inset-bottom),12px) + 56px)'
  return `<div style="${box}"><video ${attributes.join(' ')}></video></div>`
}

/** The addresses come from our own API, but building markup without escaping is a bad habit. */
function escapeAttribute(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;')
}
