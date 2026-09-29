import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { STIRRED } from '@/features/media/stirred'
import { ViewerChrome } from '@/features/media/viewer-chrome'

/** Longer than the rest, so the chrome has certainly gone. */
const AFTER_THE_REST = 4000

function aMedium(kind: 'image' | 'video'): Medium {
  return {
    id: 'medium-1',
    album_id: 'album-1',
    kind,
    status: 'active',
    taken_at: '2014-08-28T07:37:05Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: kind === 'video' ? 42 : null,
    camera_make: null,
    camera_model: null,
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: 'Urlaub/medium-1.jpg',
      filename: 'medium-1.jpg',
      byte_size: 1000,
    },
    urls: {
      thumb: '/api/v1/media/medium-1/thumb?token=a',
      preview: '/api/v1/media/medium-1/preview?token=a',
      video: kind === 'video' ? '/api/v1/media/medium-1/video?token=a' : null,
      poster: null,
      original: '/api/v1/media/medium-1/original?token=a',
    },
    files: [],
  } as unknown as Medium
}

function show(kind: 'image' | 'video') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const chromeOf = () => (
    <QueryClientProvider client={client}>
      <ViewerChrome
        medium={aMedium(kind)}
        position={{ index: 0, total: 3 }}
        onBack={() => undefined}
        onComments={() => undefined}
        onInfo={() => undefined}
        social={false}
      />
    </QueryClientProvider>
  )
  // PhotoSwipe gives its root role="dialog" and the chrome is portaled into it. The wrapper
  // stands for that root, so a tap "on the picture" is a tap inside a dialog, as it really is.
  const viewer = document.createElement('div')
  viewer.setAttribute('role', 'dialog')
  document.body.append(viewer)
  const view = render(chromeOf(), { container: viewer })
  const chrome = view.container.querySelector('[data-viewer-chrome]')
  expect(chrome).toBeInstanceOf(HTMLElement)
  return { chrome: chrome as HTMLElement, viewer }
}

/** The viewer says it: the video on screen was touched. */
function touchTheVideo() {
  act(() => {
    window.dispatchEvent(new Event(STIRRED))
  })
}

/** Nothing happens for longer than the chrome waits. */
function waitItOut() {
  act(() => {
    vi.advanceTimersByTime(AFTER_THE_REST)
  })
}

/** A finger comes down on something, the way the browser reports it. */
function tap(on: Element) {
  act(() => {
    on.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }))
  })
}

describe('the chrome over a picture', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('rests when nothing happens, and a tap on the picture brings it back', () => {
    const { chrome } = show('image')
    expect(chrome).toHaveClass('opacity-100')

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')
    expect(chrome).toHaveAttribute('aria-hidden', 'true')

    tap(document.body)
    expect(chrome).toHaveClass('opacity-100')
    expect(chrome).toHaveAttribute('aria-hidden', 'false')
  })

  it('comes back on a tap on the video too, which keeps its own tap', () => {
    // The browser draws the controls inside the video, so a tap on play is reported as a tap
    // on the video. It wakes the chrome and is not swallowed: play still plays.
    const { chrome } = show('video')
    const video = document.createElement('video')
    document.body.append(video)

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')

    const down = new PointerEvent('pointerdown', { bubbles: true, cancelable: true })
    act(() => {
      video.dispatchEvent(down)
    })

    expect(chrome).toHaveClass('opacity-100')
    expect(down.defaultPrevented).toBe(false)
    video.remove()
  })

  it('comes back when the video says it was touched, which is all a phone gives us', () => {
    // A phone keeps a tap on the media controls to itself: the window hears nothing, and the
    // buttons would stay away. The video is what reports it, and the buttons return.
    const { chrome } = show('video')

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')

    touchTheVideo()
    expect(chrome).toHaveClass('opacity-100')

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')

    // And again - not only the first touch counts.
    touchTheVideo()
    expect(chrome).toHaveClass('opacity-100')
  })

  it('wakes on a tap inside the viewer, which is a dialog itself', () => {
    // PhotoSwipe gives its root role="dialog". Turning away from every dialog meant turning
    // away from the picture as well, and no tap on one ever brought the buttons back.
    const { chrome, viewer } = show('image')
    const picture = document.createElement('img')
    viewer.append(picture)

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')

    tap(picture)
    expect(chrome).toHaveClass('opacity-100')
    picture.remove()
  })

  it('leaves a dialog opened on top of it alone', () => {
    // A confirmation over the picture answers its own taps: a name being corrected there must
    // not be spent on bringing the buttons back.
    const { chrome } = show('image')
    const over = document.createElement('div')
    over.setAttribute('role', 'dialog')
    document.body.append(over)

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')

    tap(over)
    expect(chrome).toHaveClass('opacity-0')
    over.remove()
  })

  it('rests again once the tap that woke it is over', () => {
    const { chrome } = show('image')
    waitItOut()
    tap(document.body)
    expect(chrome).toHaveClass('opacity-100')

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')
  })
})
