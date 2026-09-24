import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PersonScreen } from '@/features/people/person-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const PERSON = 'GET /api/v1/people/p1'
const FACES = 'GET /api/v1/people/p1/faces'
const PEOPLE = 'GET /api/v1/people'
const ABILITIES = 'GET /api/v1/search/abilities'
const MEDIA = 'GET /api/v1/people/p1/media'

function aFace(id: string, assignedBy: 'auto' | 'user') {
  return {
    id,
    media_id: `m-${id}`,
    crop: `/api/v1/faces/${id}/crop?token=a`,
    second: null,
    person_id: 'p1',
    assigned_by: assignedBy,
    suggested_person_id: null,
    suggested_similarity: null,
  }
}

function stub(faces: object[], extra: object = {}) {
  return stubApi({
    [PERSON]: {
      body: {
        id: 'p1',
        name: 'Olivia',
        hidden: false,
        faces: 5346,
        media: 3,
        cover: null,
        faces_auto: 4210,
        faces_twice: 12,
      },
    },
    [FACES]: { body: { items: faces, next_cursor: null } },
    [PEOPLE]: { body: { persons: [] } },
    [MEDIA]: { body: { items: [], next_cursor: null } },
    [ABILITIES]: { body: { pictures: true, meanings: true, ready: true } },
    ...extra,
  })
}

describe('a person and their faces', () => {
  it('says how large each filter is before anybody scrolls', async () => {
    // "Von Muninn zugeordnet" without a number says nothing about how much work is in it.
    stub([aFace('f1', 'auto')])
    await renderScreen(<PersonScreen personId="p1" />)

    await userEvent.click(await screen.findByRole('tab', { name: 'Gesichter' }))

    expect(screen.getByRole('button', { name: /^Alle 5\.346$/ })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /^Von Muninn zugeordnet 4\.210$/ }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Doppelt im selben Foto 12$/ })).toBeInTheDocument()
  })

  it('stands by the faces Muninn gave, and only those on the screen', async () => {
    // What Muninn decided by itself vouches for nobody. Standing by a page of it is worth more
    // than answering a hundred questions - but only what somebody has actually looked at.
    const { calls } = stub([aFace('f1', 'auto'), aFace('f2', 'auto'), aFace('f3', 'user')], {
      'POST /api/v1/faces/confirm': { body: { answered: 2 } },
    })
    await renderScreen(<PersonScreen personId="p1" />)

    await userEvent.click(await screen.findByRole('tab', { name: 'Gesichter' }))
    const stand = await screen.findByRole('button', { name: '2 Gesichter bestätigen' })
    await userEvent.click(stand)

    await waitFor(() => {
      const sent = calls.find((call) => call.path === '/api/v1/faces/confirm')
      expect(sent?.body).toEqual({ face_ids: ['f1', 'f2'] })
    })
  })

  it('offers nothing to stand by where Muninn gave nothing', async () => {
    stub([aFace('f1', 'user')])
    await renderScreen(<PersonScreen personId="p1" />)

    await userEvent.click(await screen.findByRole('tab', { name: 'Gesichter' }))

    expect(screen.queryByRole('button', { name: /bestätigen/ })).not.toBeInTheDocument()
  })
})
