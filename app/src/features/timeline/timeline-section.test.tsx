import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'
import { TimelineSection } from '@/features/timeline/timeline-section'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const MARKS = 'GET /api/v1/media/marks'
const WINDOW = 'GET /api/v1/media'
const PERIODS = 'GET /api/v1/media/periods'

function aMedium(overrides: Partial<Medium> = {}): Medium {
  const id = overrides.id ?? 'media-1'
  return {
    id,
    album_id: 'album-italien',
    kind: 'image',
    status: 'active',
    taken_at: '2014-08-28T07:37:05Z',
    taken_at_source: 'exif',
    date_is_estimated: false,
    width: 1600,
    height: 1200,
    duration_seconds: null,
    camera_make: null,
    camera_model: null,
    lens: null,
    latitude: null,
    longitude: null,
    content_hash: 'a'.repeat(64),
    has_previews: true,
    origin: {
      library_path: '/library',
      relative_path: `Autos/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 4_200_000,
    },
    urls: {
      thumb: `/api/v1/media/${id}/thumb?token=abc`,
      preview: null,
      video: null,
      poster: null,
      original: `/api/v1/media/${id}/original?token=abc`,
    },
    files: [],
    ...overrides,
  }
}

function renderRun() {
  return renderScreen(
    <TimelineSection
      columns={3}
      level="days"
      at={undefined}
      onLevelChange={vi.fn()}
      medium={undefined}
      onMediumChange={vi.fn()}
    />,
  )
}

function renderOverview(level: 'years' | 'months', at?: string, onLevelChange = vi.fn()) {
  return renderScreen(
    <TimelineSection
      columns={3}
      level={level}
      at={at}
      onLevelChange={onLevelChange}
      medium={undefined}
      onMediumChange={vi.fn()}
    />,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TimelineSection', () => {
  it('runs through the days of the library', async () => {
    stubApi({
      [MARKS]: {
        body: {
          by: 'day',
          total: 3,
          marks: [
            { start: '2014-08-28', count: 2 },
            { start: '2011-04-14', count: 1 },
          ],
        },
      },
      [WINDOW]: {
        body: {
          items: [
            aMedium({ id: 'media-1' }),
            aMedium({ id: 'media-2' }),
            aMedium({ id: 'media-3', taken_at: '2011-04-14T18:33:59Z' }),
          ],
          next_cursor: null,
          prev_cursor: null,
        },
      },
    })

    await renderRun()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Do., 28. August 2014' })).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Do., 14. April 2011' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Medium vom/ })).toHaveLength(3)
  })

  it('says how much there is and over how many years', async () => {
    stubApi({
      [MARKS]: {
        body: {
          by: 'month',
          total: 52,
          marks: [
            { start: '2014-08-01', count: 40 },
            { start: '2009-07-01', count: 12 },
          ],
        },
      },
      [WINDOW]: { body: { items: [aMedium()], next_cursor: null, prev_cursor: null } },
    })

    await renderRun()

    await waitFor(() => {
      expect(screen.getByText('52 Medien · 2009 – 2014')).toBeInTheDocument()
    })
  })

  it('marks a guessed date in the heading, not over the picture', async () => {
    stubApi({
      [MARKS]: { body: { by: 'day', total: 1, marks: [{ start: '2005-06-01', count: 1 }] } },
      [WINDOW]: {
        body: {
          items: [aMedium({ taken_at: '2005-06-01T00:00:00Z', date_is_estimated: true })],
          next_cursor: null,
          prev_cursor: null,
        },
      },
    })

    await renderRun()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /1\. Juni 2005/ })).toHaveTextContent('≈')
    })
    // The tile itself carries nothing: the heading above it already said so.
    expect(screen.getByRole('button', { name: /Medium vom/ })).not.toHaveTextContent('≈')
  })

  it('says so when the library holds nothing yet', async () => {
    stubApi({
      [MARKS]: { body: { by: 'day', total: 0, marks: [] } },
      [WINDOW]: { body: { items: [], next_cursor: null, prev_cursor: null } },
    })

    await renderRun()

    await waitFor(() => {
      expect(screen.getByText('Noch keine Medien in der Bibliothek.')).toBeInTheDocument()
    })
  })

  it('shows the library as years before anything else', async () => {
    stubApi({
      [MARKS]: { body: { by: 'month', total: 52, marks: [{ start: '2014-08-01', count: 52 }] } },
      [PERIODS]: {
        body: [
          { start: '2014-01-01', count: 40, covers: [{ id: 'media-1', thumb: '/thumb?token=a' }] },
          { start: '2009-01-01', count: 12, covers: [] },
        ],
      },
    })

    await renderOverview('years')

    expect(
      await screen.findByRole('button', { name: '2014 öffnen, 40 Medien' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '2009 öffnen, 12 Medien' })).toBeInTheDocument()
  })

  it('steps into the months of the year that was chosen', async () => {
    const onLevelChange = vi.fn()
    stubApi({
      [MARKS]: { body: { by: 'month', total: 40, marks: [{ start: '2014-08-01', count: 40 }] } },
      [PERIODS]: { body: [{ start: '2014-01-01', count: 40, covers: [] }] },
    })

    await renderOverview('years', undefined, onLevelChange)
    await userEvent.click(await screen.findByRole('button', { name: '2014 öffnen, 40 Medien' }))

    expect(onLevelChange).toHaveBeenCalledWith('months', '2014')
  })

  it('offers the way back out of a level', async () => {
    const onLevelChange = vi.fn()
    stubApi({
      [MARKS]: { body: { by: 'month', total: 40, marks: [{ start: '2014-08-01', count: 40 }] } },
      [PERIODS]: { body: [{ start: '2014-08-01', count: 40, covers: [] }] },
    })

    await renderOverview('months', '2014', onLevelChange)
    await userEvent.click(await screen.findByRole('button', { name: 'Jahre' }))

    expect(onLevelChange).toHaveBeenCalledWith('years', undefined)
  })
})
