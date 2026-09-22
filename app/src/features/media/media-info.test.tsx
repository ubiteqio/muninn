import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { MediaInfo } from '@/features/media/media-info'

function aMedium(overrides: Partial<Medium> = {}): Medium {
  return {
    id: 'media-1',
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
    lens: 'EF-S 18-55mm',
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: '2009 Italien/Venedig/IMG_1.jpg',
      filename: 'IMG_1.jpg',
      byte_size: 4_200_000,
    },
    urls: {
      thumb: null,
      preview: null,
      video: null,
      poster: null,
      original: '/api/v1/media/media-1/original?token=abc',
    },
    files: [
      {
        role: 'primary',
        filename: 'IMG_1.jpg',
        relative_path: '2009 Italien/Venedig/IMG_1.jpg',
        byte_size: 4_200_000,
        content_hash: 'a'.repeat(64),
      },
    ],
    ...overrides,
  }
}

describe('MediaInfo', () => {
  it('stays out of the way until it is asked for', () => {
    render(<MediaInfo medium={aMedium()} open={false} onClose={vi.fn()} />)

    expect(screen.queryByRole('complementary')).toBeNull()
  })

  it('says when the picture was taken, with what, and where it lies', () => {
    render(<MediaInfo medium={aMedium()} open onClose={vi.fn()} />)

    expect(screen.getByText(/14\. Juli 2009/)).toBeInTheDocument()
    expect(screen.getByText('aus den Bilddaten')).toBeInTheDocument()
    expect(screen.getByText('Canon EOS 400D')).toBeInTheDocument()
    expect(screen.getByText('1600 × 1200 Pixel')).toBeInTheDocument()
    expect(screen.getByText('IMG_1.jpg')).toBeInTheDocument()
    // The size is here rather than on the download button, which is an icon in the bar above.
    expect(screen.getByText('4,2 MB')).toBeInTheDocument()
    expect(screen.getByText('2009 Italien/Venedig')).toBeInTheDocument()
  })

  it('marks a date that was only guessed', () => {
    const guessed = aMedium({ taken_at_source: 'folder_name', date_is_estimated: true })

    render(<MediaInfo medium={guessed} open onClose={vi.fn()} />)

    expect(screen.getByText(/aus dem Ordnernamen · Datum geschätzt/)).toBeInTheDocument()
  })

  it('shows a video by its length, not its megapixels', () => {
    const video = aMedium({ kind: 'video', duration_seconds: 64.4, width: 1920, height: 1080 })

    render(<MediaInfo medium={video} open onClose={vi.fn()} />)

    expect(screen.getByText('1:04')).toBeInTheDocument()
    expect(screen.getByText('1920 × 1080')).toBeInTheDocument()
  })

  it('puts what the AI saw first: the sentence, its words and the text in the picture', () => {
    render(
      <MediaInfo
        medium={aMedium()}
        open
        onClose={vi.fn()}
        analysis={{
          caption: 'Zwei Kinder bauen am Strand eine Sandburg.',
          tags: ['strand', 'kinder', 'sandburg'],
          scene: 'strand',
          ocr_text: 'Lido di Jesolo',
          model: 'qwen',
          analyzed_at: '2026-09-21T08:00:00Z',
          moments: [],
        }}
      />,
    )

    expect(screen.getByText('Zwei Kinder bauen am Strand eine Sandburg.')).toBeInTheDocument()
    const tags = screen.getByRole('list', { name: 'Stichwörter' })
    expect(tags.textContent).toBe('strandkindersandburg')
    expect(screen.getByText('Lido di Jesolo')).toBeInTheDocument()
  })

  it('goes without a description until there is one', () => {
    render(<MediaInfo medium={aMedium()} open onClose={vi.fn()} analysis={null} />)

    expect(screen.queryByRole('region', { name: 'Beschreibung' })).toBeNull()
  })

  it('names the place when the camera knew it', () => {
    const located = aMedium({ latitude: 45.4372, longitude: 12.3345 })

    render(<MediaInfo medium={located} open onClose={vi.fn()} />)

    expect(screen.getByText('45,4372° N, 12,3345° O')).toBeInTheDocument()
  })

  it('names the town once it is known, and a city state only once', () => {
    const venice = aMedium({
      latitude: 45.4372,
      longitude: 12.3345,
      place: {
        id: 3164603,
        name: 'Venedig',
        region: 'Venetien',
        country: 'Italien',
        estimated: false,
      },
    })
    const hamburg = aMedium({
      latitude: 53.55,
      longitude: 9.99,
      place: {
        id: 2911298,
        name: 'Hamburg',
        region: 'Hamburg',
        country: 'Deutschland',
        estimated: false,
      },
    })

    const { unmount } = render(<MediaInfo medium={venice} open onClose={vi.fn()} />)
    expect(screen.getByText('Venedig, Venetien, Italien')).toBeInTheDocument()
    expect(screen.getByText('45,4372° N, 12,3345° O · Ortsnamen: GeoNames')).toBeInTheDocument()
    unmount()

    render(<MediaInfo medium={hamburg} open onClose={vi.fn()} />)
    expect(screen.getByText('Hamburg, Deutschland')).toBeInTheDocument()
  })

  it("says when the place is only the album's", () => {
    const scanned = aMedium({
      place: {
        id: 3176959,
        name: 'Florenz',
        region: 'Toskana',
        country: 'Italien',
        estimated: true,
      },
    })

    render(<MediaInfo medium={scanned} open onClose={vi.fn()} />)

    expect(screen.getByText('Florenz, Toskana, Italien')).toBeInTheDocument()
    expect(
      screen.getByText('Geschätzt aus dem Ort des Albums · Ortsnamen: GeoNames'),
    ).toBeInTheDocument()
  })

  it('names what lies beside the original', () => {
    const withRaw = aMedium({
      files: [
        ...aMedium().files,
        {
          role: 'raw',
          filename: 'IMG_1.CR2',
          relative_path: '2009 Italien/Venedig/IMG_1.CR2',
          byte_size: 12_000_000,
          content_hash: 'b'.repeat(64),
        },
      ],
    })

    render(<MediaInfo medium={withRaw} open onClose={vi.fn()} />)

    expect(screen.getByText('IMG_1.CR2')).toBeInTheDocument()
  })

  it('can be closed again', async () => {
    const onClose = vi.fn()
    render(<MediaInfo medium={aMedium()} open onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: 'Schließen' }))

    expect(onClose).toHaveBeenCalledOnce()
  })
})
