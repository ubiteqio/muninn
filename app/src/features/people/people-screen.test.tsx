import { useSearch } from '@tanstack/react-router'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PeopleScreen } from '@/features/people/people-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aFace(id: string) {
  return {
    id,
    media_id: `m-${id}`,
    box: { left: 0.1, top: 0.1, right: 0.3, bottom: 0.4 },
    second: null,
    crop: `/crop/${id}`,
    person_id: null,
    assigned_by: null,
    suggested_person_id: null,
  }
}

const OVERVIEW = {
  persons: [
    {
      id: 'lena',
      name: 'Lena',
      hidden: false,
      faces: 40,
      media: 31,
      cover: aFace('cover'),
    },
  ],
  groups: {
    items: [{ cluster: 7, size: 5, faces: [aFace('g1'), aFace('g2')] }],
    next_cursor: null,
  },
  suggestions: 1,
}

describe('PeopleScreen', () => {
  it('keeps the page in shape while the answers are on their way', async () => {
    // Without the placeholders the groups arrive first and push the rest down as it lands.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    )

    await renderScreen(<PeopleScreen />)

    for (const title of ['Personen', 'Vorschläge', 'Wer ist das?']) {
      const section = screen.getByRole('region', { name: title })
      expect(section).toHaveAttribute('aria-busy', 'true')
      expect(within(section).getByText('Wird geladen …')).toBeInTheDocument()
    }
    vi.unstubAllGlobals()
  })

  it('names a group, answers a suggestion and lists the persons', async () => {
    const { calls } = stubApi({
      'GET /api/v1/people': { body: OVERVIEW },
      'GET /api/v1/people/groups': { body: OVERVIEW.groups },
      'GET /api/v1/people/groups/7': { body: [aFace('g1'), aFace('g2'), aFace('g3')] },
      'GET /api/v1/people/suggestions': {
        body: {
          items: [
            {
              face: { ...aFace('s1'), suggested_similarity: 0.52 },
              person: { id: 'lena', name: 'Lena' },
            },
          ],
          next_cursor: null,
        },
      },
      'POST /api/v1/people/groups/7/name': { body: { id: 'oma', name: 'Oma' } },
      'POST /api/v1/faces/s1/confirm': { status: 204 },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)

    expect(await screen.findByText('Ist das Lena?')).toBeInTheDocument()
    expect(screen.getByText('Ähnlichkeit 52 %')).toBeInTheDocument()
    expect(screen.getByText('31 Fotos')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ja, das ist Lena' }))
    await waitFor(() => {
      expect(calls.some((call) => call.path === '/api/v1/faces/s1/confirm')).toBe(true)
    })

    await user.click(screen.getByRole('button', { name: 'Gruppe mit 5 Gesichtern benennen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'Oma')
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }))

    await waitFor(() => {
      expect(calls.find((call) => call.path === '/api/v1/people/groups/7/name')?.body).toEqual({
        name: 'Oma',
      })
    })
  })
})

describe('a suggestion, looked at closer', () => {
  it('shows the photo with the face and the person to compare, and answers from there', async () => {
    const { calls } = stubApi({
      'GET /api/v1/people': { body: OVERVIEW },
      'GET /api/v1/people/groups': { body: OVERVIEW.groups },
      'GET /api/v1/people/suggestions': {
        body: {
          items: [{ face: aFace('s1'), person: { id: 'lena', name: 'Lena' } }],
          next_cursor: null,
        },
      },
      'GET /api/v1/media/m-s1': {
        body: {
          id: 'm-s1',
          origin: {
            library_path: '/library',
            relative_path: 'Kinder/Alle/Simon/2017-04-16 – Simon in München/XDMU1149.png',
            filename: 'XDMU1149.png',
            byte_size: 1024,
          },
          urls: {
            thumb: '/t',
            preview: '/preview/m-s1',
            video: null,
            poster: null,
            original: '/o',
          },
        },
      },
      'GET /api/v1/people/lena/faces': {
        body: { items: [aFace('k1'), aFace('k2')], next_cursor: null },
      },
      'POST /api/v1/faces/s1/reject': { status: 204 },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)
    await user.click(await screen.findByRole('button', { name: 'Größer ansehen, ob das Lena ist' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Schon Lena')).toBeInTheDocument()
    await waitFor(() => {
      expect(dialog.querySelector('img[src="/preview/m-s1"]')).not.toBeNull()
    })
    // Two babies are the same face to anybody; the folder is what tells them apart, and the
    // whole way there is on the mouseover.
    const folder = await within(dialog).findByText('2017-04-16 – Simon in München')
    expect(folder.closest('p')).toHaveAttribute(
      'title',
      'Kinder/Alle/Simon/2017-04-16 – Simon in München',
    )
    await user.click(within(dialog).getByRole('button', { name: /Nicht Lena/ }))

    await waitFor(() => {
      expect(calls.some((call) => call.path === '/api/v1/faces/s1/reject')).toBe(true)
    })
  })
})

describe('a wrong suggestion', () => {
  const WITH_MIA = {
    ...OVERVIEW,
    persons: [
      ...OVERVIEW.persons,
      { id: 'mia', name: 'Mia', hidden: false, faces: 3, media: 3, cover: aFace('mia') },
    ],
  }
  const SUGGESTIONS = {
    items: [{ face: aFace('s1'), person: { id: 'lena', name: 'Lena' } }],
    next_cursor: null,
  }

  it('goes to another person there is, picked with one tap', async () => {
    const { calls } = stubApi({
      'GET /api/v1/people': { body: WITH_MIA },
      'GET /api/v1/people/groups': { body: OVERVIEW.groups },
      'GET /api/v1/people/suggestions': { body: SUGGESTIONS },
      'POST /api/v1/faces/s1/name': { body: { id: 'mia', name: 'Mia' } },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)
    await user.click(await screen.findByRole('button', { name: 'Jemand anderes' }))

    const dialog = await screen.findByRole('dialog', { name: 'Nicht Lena – wer ist es?' })
    // The person it is not is not offered again.
    expect(within(dialog).queryByRole('button', { name: 'Lena' })).toBeNull()
    await user.click(within(dialog).getByRole('button', { name: 'Mia' }))

    await waitFor(() => {
      expect(calls.find((call) => call.path === '/api/v1/faces/s1/name')?.body).toEqual({
        name: 'Mia',
      })
    })
  })

  it('or to a new person, said to be new before it is saved', async () => {
    const { calls } = stubApi({
      'GET /api/v1/people': { body: WITH_MIA },
      'GET /api/v1/people/groups': { body: OVERVIEW.groups },
      'GET /api/v1/people/suggestions': { body: SUGGESTIONS },
      'POST /api/v1/faces/s1/name': { body: { id: 'opa', name: 'Opa' } },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)
    await user.click(await screen.findByRole('button', { name: 'Jemand anderes' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'Opa')

    expect(within(dialog).getByText(/wird als neue Person angelegt/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }))
    await waitFor(() => {
      expect(calls.find((call) => call.path === '/api/v1/faces/s1/name')?.body).toEqual({
        name: 'Opa',
      })
    })
  })
})

describe('the persons, page by page', () => {
  const NAMES = [
    'Mats',
    'Oskar',
    'Boris',
    'Greta',
    'Michael',
    'Rita',
    'Hilde',
    'Mila',
    'Amira',
    'Paul',
    'Benjamin',
    'Dora',
    'Jonas',
    'Emil',
    'Lotte',
    'Jakob',
    'Ömer',
  ]
  const MANY = {
    ...OVERVIEW,
    // The server's order does not matter: the most photographed come first.
    persons: NAMES.map((name, index) => ({
      id: name.toLowerCase(),
      name,
      hidden: false,
      faces: 10,
      media: 100 - index,
      cover: aFace(name),
    })).reverse(),
    suggestions: 0,
  }

  /** As the route does: the address hands letter and page to the screen. */
  function Routed() {
    const search = useSearch({ strict: false })
    return <PeopleScreen {...search} />
  }

  function names() {
    return within(screen.getByRole('region', { name: 'Personen' }))
      .getAllByRole('link')
      .map((link) => link.textContent.replace(/\d+ Fotos?$/, ''))
  }

  it('shows fourteen at a time, the most photographed first, and turns the page', async () => {
    stubApi({
      'GET /api/v1/people': { body: MANY },
      'GET /api/v1/people/groups': { body: { items: [], next_cursor: null } },
    })
    const user = userEvent.setup()

    await renderScreen(<Routed />, { path: '/people' })

    await screen.findByText('Mats')
    expect(names()).toEqual(NAMES.slice(0, 14))
    expect(screen.getByText('1–14 von 17 Personen')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Nächste Seite' }))

    await waitFor(() => {
      expect(names()).toEqual(NAMES.slice(14))
    })
    expect(screen.getByRole('button', { name: 'Seite 2' })).toHaveAttribute('aria-current', 'page')
  })

  it('narrows to one letter, umlauts under their plain letter, and back to all', async () => {
    stubApi({
      'GET /api/v1/people': { body: MANY },
      'GET /api/v1/people/groups': { body: { items: [], next_cursor: null } },
    })
    const user = userEvent.setup()

    await renderScreen(<Routed />, { path: '/people' })
    await screen.findByText('Mats')

    // Nobody's name starts with a Q.
    expect(screen.getByRole('button', { name: 'Q: 0 Personen' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'O: 2 Personen' }))

    await waitFor(() => {
      expect(names()).toEqual(['Oskar', 'Ömer'])
    })
    expect(screen.queryByRole('navigation', { name: 'Seiten' })).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Alle' }))
    await waitFor(() => {
      expect(names()).toHaveLength(14)
    })
  })
})

describe('AlikeDialog', () => {
  const ALIKE = {
    person_id: 'lena',
    items: [
      { face: aFace('a1'), similarity: 0.93 },
      { face: aFace('a2'), similarity: 0.84 },
      { face: aFace('a3'), similarity: 0.66 },
    ],
  }

  function stubPeople(extra: Record<string, unknown>) {
    return stubApi({
      'GET /api/v1/people': { body: { ...OVERVIEW, groups: { items: [], next_cursor: null } } },
      'GET /api/v1/people/groups': { body: { items: [], next_cursor: null } },
      'GET /api/v1/people/suggestions': {
        body: {
          items: [
            {
              face: { ...aFace('s1'), suggested_similarity: 0.52 },
              person: { id: 'lena', name: 'Lena' },
            },
          ],
          next_cursor: null,
        },
      },
      'POST /api/v1/faces/s1/confirm': { status: 204 },
      ...extra,
    })
  }

  it('offers the faces that look the same and answers them together', async () => {
    const { calls } = stubPeople({
      'GET /api/v1/faces/s1/alike': { body: ALIKE },
      'POST /api/v1/faces/alike': { body: { answered: 2 } },
    })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)
    await user.click(await screen.findByRole('button', { name: 'Ja, das ist Lena' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Diese auch als Lena?')).toBeInTheDocument()
    // The line sits at 80 %, so the third face is below it and not offered.
    expect(within(dialog).getByText('2 Gesichter werden übernommen')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: '2 übernehmen' }))

    await waitFor(() => {
      const sent = calls.find((call) => call.path === '/api/v1/faces/alike')
      expect(sent?.body).toEqual({ person_id: 'lena', face_ids: ['a1', 'a2'], confirm: true })
    })
  })

  it('keeps out of the way when nothing looks the same', async () => {
    stubPeople({ 'GET /api/v1/faces/s1/alike': { body: { person_id: 'lena', items: [] } } })
    const user = userEvent.setup()

    await renderScreen(<PeopleScreen />)
    await user.click(await screen.findByRole('button', { name: 'Ja, das ist Lena' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })
})
