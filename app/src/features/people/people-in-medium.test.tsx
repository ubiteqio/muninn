import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { PeopleInMedium } from '@/features/people/people-in-medium'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aFace(id: string) {
  return {
    id,
    media_id: 'm1',
    box: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.4 },
    second: null,
    crop: `/crop/${id}`,
    person_id: null,
    assigned_by: null,
    suggested_person_id: null,
    suggested_similarity: null,
  }
}

const FACES = [
  { face: aFace('f1'), person: null, suggested: null },
  { face: aFace('f2'), person: null, suggested: { id: 'mia', name: 'Mia' } },
  { face: aFace('f3'), person: { id: 'boris', name: 'Boris' }, suggested: null },
]

const PEOPLE = {
  persons: [
    { id: 'boris', name: 'Boris', hidden: false, faces: 9, media: 9, cover: aFace('b') },
    { id: 'greta', name: 'Greta', hidden: false, faces: 4, media: 4, cover: aFace('a') },
  ],
  groups: { items: [], next_cursor: null },
  suggestions: 0,
}

describe('PeopleInMedium', () => {
  it('shows the named first, then the guesses, then the unknown', async () => {
    stubApi({ 'GET /api/v1/media/m1/faces': { body: FACES } })

    await renderScreen(<PeopleInMedium mediaId="m1" />)

    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(3)
    const text = items.map((item) => item.textContent)
    expect(text[0]).toMatch(/^Boris/)
    expect(text[1]).toMatch(/^Mia\?/)
    expect(
      within(items[2] as HTMLElement).getByRole('button', { name: 'Wer ist das?' }),
    ).toBeInTheDocument()
    // A name opens the search for the photos with that person.
    expect(within(items[0] as HTMLElement).getByRole('link', { name: /Boris/ })).toHaveAttribute(
      'href',
      '/search?q=Boris',
    )
  })

  it('takes a wrongly named face from its person', async () => {
    const { calls } = stubApi({
      'GET /api/v1/media/m1/faces': { body: FACES },
      'POST /api/v1/faces/f3/reject': { status: 204 },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleInMedium mediaId="m1" />)
    await user.click(await screen.findByRole('button', { name: /Nicht Boris/ }))

    await waitFor(() => {
      expect(calls.some((call) => call.path === '/api/v1/faces/f3/reject')).toBe(true)
    })
  })

  it('gives a named face to another person', async () => {
    const { calls } = stubApi({
      'GET /api/v1/media/m1/faces': { body: FACES },
      'GET /api/v1/people': { body: PEOPLE },
      'POST /api/v1/faces/f3/name': { body: { id: 'greta', name: 'Greta' } },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleInMedium mediaId="m1" />)
    await user.click(
      await screen.findByRole('button', { name: 'Andere Person statt Boris zuordnen' }),
    )

    const dialog = await screen.findByRole('dialog', { name: 'Nicht Boris – wer ist es?' })
    expect(within(dialog).queryByRole('button', { name: 'Boris' })).toBeNull()
    await user.click(await within(dialog).findByRole('button', { name: 'Greta' }))

    await waitFor(() => {
      expect(calls.find((call) => call.path === '/api/v1/faces/f3/name')?.body).toEqual({
        name: 'Greta',
      })
    })
  })
})
