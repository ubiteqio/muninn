import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { GroupScreen } from '@/features/people/group-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const FACES = 'GET /api/v1/people/groups/7'
const MEDIA = 'GET /api/v1/people/groups/7/media'
const PEOPLE = 'GET /api/v1/people'
const ABILITIES = 'GET /api/v1/search/abilities'

function aFace(id: string) {
  return {
    id,
    media_id: `m-${id}`,
    crop: `/api/v1/faces/${id}/crop?token=a`,
    second: null,
    person_id: null,
    assigned_by: null,
    suggested_person_id: null,
    suggested_similarity: null,
  }
}

function aMedium(id: string) {
  return {
    id,
    album_id: 'album-1',
    kind: 'image' as const,
    status: 'active' as const,
    taken_at: '2018-03-24T15:30:12Z',
    taken_at_source: 'exif' as const,
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
      root_id: 'root-1',
      root_name: 'Fotos',
      relative_path: `Fest/${id}.jpg`,
      filename: `${id}.jpg`,
      byte_size: 30801,
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

function stub(faces: object[], media: object[], extra: object = {}) {
  return stubApi({
    [FACES]: { body: faces },
    [MEDIA]: { body: { items: media, next_cursor: null } },
    [PEOPLE]: { body: { persons: [] } },
    [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } },
    ...extra,
  })
}

describe('an unnamed group, laid out like an album', () => {
  it('shows every photo the group is in, and names it from there', async () => {
    const { calls } = stub(
      [aFace('g1'), aFace('g2'), aFace('g3')],
      [aMedium('m1'), aMedium('m2')],
      {
        'POST /api/v1/people/groups/7/name': { body: { id: 'oma', name: 'Oma' } },
      },
    )
    const user = userEvent.setup()
    const { router } = await renderScreen(<GroupScreen cluster={7} />)

    expect(await screen.findByText('3 Gesichter')).toBeInTheDocument()
    expect(await screen.findAllByRole('button', { name: /^Medium vom .* öffnen$/ })).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: 'Benennen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'Oma')
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/people/oma')
    })
    expect(calls.find((call) => call.path === '/api/v1/people/groups/7/name')?.body).toEqual({
      name: 'Oma',
    })
  })

  it('says so when the group was named in the meantime', async () => {
    // A link kept from before: the faces have a person now, and the group is gone.
    stub([], [])
    await renderScreen(<GroupScreen cluster={7} />)

    expect(
      await screen.findByText(
        'Diese Gruppe gibt es nicht mehr. Vielleicht hat sie schon jemand benannt.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Benennen' })).toBeDisabled()
  })
})
