import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
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
  const view = render(
    <QueryClientProvider client={client}>
      <ViewerChrome
        medium={aMedium(kind)}
        position={{ index: 0, total: 3 }}
        onBack={() => undefined}
        onComments={() => undefined}
        onInfo={() => undefined}
        social={false}
      />
    </QueryClientProvider>,
  )
  const chrome = view.container.querySelector('[data-viewer-chrome]')
  expect(chrome).toBeInstanceOf(HTMLElement)
  return chrome as HTMLElement
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
    const chrome = show('image')
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
    const chrome = show('video')
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

  it('rests again once the tap that woke it is over', () => {
    const chrome = show('image')
    waitItOut()
    tap(document.body)
    expect(chrome).toHaveClass('opacity-100')

    waitItOut()
    expect(chrome).toHaveClass('opacity-0')
  })
})
