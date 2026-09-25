import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { useAuthStore } from '@/features/auth/auth-store'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aMedium(id: string): Medium {
  return {
    id,
    album_id: 'album-italien',
    kind: 'image',
    status: 'active',
    taken_at: '2009-07-14T15:30:12Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: null,
    camera_make: 'Canon',
    camera_model: 'EOS 400D',
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: `2009 Italien/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 4_200_000,
    },
    urls: {
      thumb: `/api/v1/media/${id}/thumb?token=abc`,
      preview: `/api/v1/media/${id}/preview?token=abc`,
      video: null,
      poster: null,
      original: `/api/v1/media/${id}/original?token=abc`,
    },
    files: [],
  }
}

function aVideo(id: string): Medium {
  const medium = aMedium(id)
  return {
    ...medium,
    kind: 'video',
    duration_seconds: 12,
    urls: { ...medium.urls, video: `/api/v1/media/${id}/video?token=abc`, poster: null },
  }
}

const MEDIA = [aMedium('media-1'), aMedium('media-2')]

function Album({
  current,
  onCurrentChange = vi.fn(),
  social = false,
  media = MEDIA,
}: {
  current?: string | undefined
  onCurrentChange?: (id: string | undefined) => void
  social?: boolean
  media?: Medium[]
}) {
  const viewer = useMediaViewer(media, { current, onCurrentChange, social })

  return (
    <div>
      <button
        type="button"
        onClick={() => {
          viewer.open(1)
        }}
      >
        Zweites öffnen
      </button>
      {viewer.panel}
    </div>
  )
}

const gallery = () => document.querySelector('.pswp')

describe('useMediaViewer', () => {
  it('shows nothing while the address names no medium', async () => {
    await renderScreen(<Album />)

    expect(gallery()).toBeNull()
  })

  it('opens the medium the address asks for', async () => {
    await renderScreen(<Album current="media-1" />)

    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })
  })

  it('closes again when the medium leaves the address', async () => {
    function Album2() {
      const [current, setCurrent] = useState<string | undefined>('media-1')
      return (
        <div>
          <button
            type="button"
            onClick={() => {
              setCurrent(undefined)
            }}
          >
            Schliessen
          </button>
          <Album current={current} onCurrentChange={setCurrent} />
        </div>
      )
    }
    await renderScreen(<Album2 />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Schliessen' }))

    await waitFor(() => {
      expect(gallery()).toBeNull()
    })
  })

  it('opens nothing by itself: a click writes the medium into the address', async () => {
    const onCurrentChange = vi.fn()
    await renderScreen(<Album onCurrentChange={onCurrentChange} />)

    await userEvent.click(screen.getByRole('button', { name: 'Zweites öffnen' }))

    expect(onCurrentChange).toHaveBeenCalledWith('media-2')
    expect(gallery()).toBeNull()
  })

  it('hands the original to the browser, under its name from the NAS', async () => {
    const clicks: { href: string; download: string }[] = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicks.push({ href: this.getAttribute('href') ?? '', download: this.download })
    })
    await renderScreen(<Album current="media-2" />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Original laden' }))

    expect(clicks).toEqual([
      { href: '/api/v1/media/media-2/original?token=abc&download=1', download: 'media-2.jpg' },
    ])
    click.mockRestore()
  })

  it('carries the details of the picture on screen, with what the AI saw', async () => {
    stubApi({
      'GET /api/v1/media/media-2': {
        body: {
          ...MEDIA[1],
          analysis: {
            caption: 'Ein Gondoliere auf dem Canal Grande.',
            tags: ['venedig'],
            scene: 'stadt',
            ocr_text: '',
            model: 'qwen',
            analyzed_at: '2026-09-21T08:00:00Z',
            moments: [],
          },
          transcript: null,
        },
      },
    })
    await renderScreen(<Album current="media-2" />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Details anzeigen' }))

    const details = screen.getByRole('complementary', { name: 'Details' })
    expect(within(details).getByText('media-2.jpg')).toBeInTheDocument()
    expect(within(details).getByText('Ein Gondoliere auf dem Canal Grande.')).toBeInTheDocument()
  })

  it('closes the details with a tap beside them, and keeps them for a tap inside', async () => {
    stubApi({
      'GET /api/v1/media/media-2': { body: { ...MEDIA[1], analysis: null, transcript: null } },
    })
    await renderScreen(<Album current="media-2" />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Details anzeigen' }))
    const details = await screen.findByRole('complementary', { name: 'Details' })
    await user.click(within(details).getByText('media-2.jpg'))
    expect(screen.getByRole('complementary', { name: 'Details' })).toBeInTheDocument()

    await user.click(document.querySelector('.pswp__scroll-wrap') as HTMLElement)
    await waitFor(() => {
      expect(screen.queryByRole('complementary', { name: 'Details' })).not.toBeInTheDocument()
    })
    // That tap only closed the panel: the picture is still on screen.
    expect(gallery()).not.toBeNull()
  })

  it('opens the comments in a panel of their own from the speech bubble, not the details', async () => {
    stubApi({
      'GET /api/v1/media/media-2': { body: { ...MEDIA[1], analysis: null, transcript: null } },
      'GET /api/v1/media/media-2/social': {
        body: {
          likes: 0,
          liked: false,
          likers: [],
          favorite: false,
          comments: 1,
          reactions: [],
          people: [],
        },
      },
      'GET /api/v1/media/media-2/comments': { body: { count: 0, items: [] } },
      'GET /api/v1/people/mentionable': { body: [] },
    })
    await renderScreen(<Album current="media-2" social />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Kommentare' }))

    const comments = await screen.findByRole('complementary', { name: 'Kommentare' })
    expect(within(comments).getByRole('textbox', { name: 'Kommentieren …' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Details' })).not.toBeInTheDocument()

    // The details carry no conversation any more, and only one panel is open at a time.
    await user.click(screen.getByRole('button', { name: 'Details anzeigen' }))
    const details = await screen.findByRole('complementary', { name: 'Details' })
    expect(within(details).queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Kommentare' })).not.toBeInTheDocument()
  })

  it('starts the video one opens, and the one moved on to', async () => {
    // Opening a film is asking to watch it; a second tap on play is a tap too many.
    const played = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)

    try {
      await renderScreen(<Album current="film-1" media={[aVideo('film-1'), aVideo('film-2')]} />)

      await waitFor(() => {
        expect(played).toHaveBeenCalled()
      })
    } finally {
      played.mockRestore()
    }
  })

  it('offers an admin what the pipeline can do to the picture, and nobody else', async () => {
    stubApi({
      'GET /api/v1/media/media-2': { body: { ...MEDIA[1], analysis: null, transcript: null } },
      'GET /api/v1/media/media-2/faces': { body: [] },
      'GET /api/v1/media/media-2/stages': {
        body: {
          media_id: 'media-2',
          stages: [
            { stage: 'derive', state: 'done', attempts: 0, last_error: null },
            {
              stage: 'faces',
              state: 'given-up',
              attempts: 3,
              last_error: 'no frame could be read',
            },
          ],
        },
      },
    })
    useAuthStore.setState({
      status: 'signed-in',
      needsPasswordChange: false,
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        username: 'odin',
        email: 'odin@muninn.local',
        display_name: 'Odin',
        role: 'admin',
        status: 'active',
        must_change_password: false,
        created_at: '2026-09-01T10:00:00Z',
        last_login_at: '2026-09-23T10:00:00Z',
      },
    })
    await renderScreen(<Album current="media-2" />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    await userEvent.click(screen.getByRole('button', { name: 'KI-Werkzeuge' }))

    expect(await screen.findByText('Gesichter suchen')).toBeInTheDocument()
    expect(screen.getByText('Aufgegeben nach 3 Versuchen')).toBeInTheDocument()
    expect(screen.getByText('no frame could be read')).toBeInTheDocument()
    // Taking a picture down is what somebody reaches for in a hurry: it stands first, not
    // under seven steps of a pipeline.
    expect(screen.getByText('Medium entfernen')).toBeInTheDocument()
  })

  it('takes a picture down only after asking, and names the file', async () => {
    const { calls } = stubApi({
      'GET /api/v1/media/media-2': { body: { ...MEDIA[1], analysis: null, transcript: null } },
      'GET /api/v1/media/media-2/faces': { body: [] },
      'GET /api/v1/media/media-2/stages': { body: { media_id: 'media-2', stages: [] } },
      'DELETE /api/v1/media/media-2': { status: 204 },
    })
    useAuthStore.setState({
      status: 'signed-in',
      needsPasswordChange: false,
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        username: 'odin',
        email: 'odin@muninn.local',
        display_name: 'Odin',
        role: 'admin',
        status: 'active',
        must_change_password: false,
        created_at: '2026-09-01T10:00:00Z',
        last_login_at: '2026-09-23T10:00:00Z',
      },
    })
    await renderScreen(<Album current="media-2" />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    // The buttons rest after a few seconds, and the tap that brings them back is spent on
    // that alone - so the menu takes a second one, exactly as it does on a phone.
    const menu = screen.getAllByRole('button', { name: 'KI-Werkzeuge' }).at(-1) as HTMLElement
    await userEvent.click(menu)
    if (menu.getAttribute('data-state') === 'closed') await userEvent.click(menu)
    await userEvent.click(await screen.findByText('Medium entfernen'))

    // Asked first, with the file named, and nothing sent until it is answered.
    expect(await screen.findByText('Medium wirklich entfernen?')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: 'Endgültig entfernen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
    })
  })

  it('stops the video of the picture one leaves behind', async () => {
    // PhotoSwipe keeps the neighbouring slides in the DOM, and a video taken out of the page
    // carries on with its sound. Moving on has to stop it.
    const paused = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})

    function Films() {
      const [current, setCurrent] = useState<string | undefined>('film-1')
      const viewer = useMediaViewer([aVideo('film-1'), aVideo('film-2')], {
        current,
        onCurrentChange: setCurrent,
      })

      return (
        <div>
          <button
            type="button"
            onClick={() => {
              setCurrent('film-2')
            }}
          >
            Weiter
          </button>
          {viewer.panel}
        </div>
      )
    }

    try {
      await renderScreen(<Films />)
      await waitFor(() => {
        expect(document.querySelectorAll('video').length).toBeGreaterThan(0)
      })

      await userEvent.click(screen.getByRole('button', { name: 'Weiter' }))

      await waitFor(() => {
        expect(paused).toHaveBeenCalled()
      })
    } finally {
      paused.mockRestore()
    }
  })

  it('offers pictures like the one on screen when asked to', async () => {
    const asked: string[] = []
    function Search() {
      const viewer = useMediaViewer(MEDIA, {
        current: 'media-2',
        onCurrentChange: vi.fn(),
        onSimilar: (id) => {
          asked.push(id)
        },
      })
      return <div>{viewer.panel}</div>
    }
    await renderScreen(<Search />)
    await waitFor(() => {
      expect(gallery()).not.toBeNull()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Ähnliche Bilder' }))

    expect(asked).toEqual(['media-2'])
  })
})
