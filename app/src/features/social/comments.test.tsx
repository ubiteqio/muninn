import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CommentsSection } from '@/features/social/comments'
import { SocialRail } from '@/features/social/social-rail'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const COMMENTS = 'GET /api/v1/media/media-1/comments'
const PEOPLE = 'GET /api/v1/people/mentionable'

function aComment(id: string, body: string, name = 'Anna', extra: object = {}) {
  return {
    id,
    author: { id: `user-${name}`, display_name: name, username: name.toLowerCase() },
    body,
    created_at: new Date().toISOString(),
    edited_at: null,
    deleted: false,
    likes: 0,
    liked: false,
    can_edit: false,
    can_delete: false,
    replies: [],
    ...extra,
  }
}

describe('CommentsSection', () => {
  it('shows a conversation with its answers and who is named in it', async () => {
    stubApi({
      [COMMENTS]: {
        body: {
          count: 2,
          items: [
            aComment('c1', 'Wo war das, @boris?', 'Anna', {
              replies: [aComment('c2', 'In Venedig!', 'Boris')],
            }),
          ],
        },
      },
      [PEOPLE]: { body: [] },
    })

    await renderScreen(<CommentsSection target={{ kind: 'media', id: 'media-1' }} />)

    expect(await screen.findByText('In Venedig!')).toBeInTheDocument()
    expect(screen.getByText('@boris')).toHaveClass('text-accent')
    expect(screen.getByText('Anna')).toBeInTheDocument()
  })

  it('offers the people who can be named and writes the comment with Enter', async () => {
    const { calls } = stubApi({
      [COMMENTS]: { body: { count: 0, items: [] } },
      [PEOPLE]: {
        body: [
          { id: 'u1', username: 'boris', display_name: 'Boris' },
          { id: 'u2', username: 'lena', display_name: 'Lena' },
        ],
      },
      'POST /api/v1/media/media-1/comments': { status: 201, body: aComment('c1', 'x') },
    })
    await renderScreen(<CommentsSection target={{ kind: 'media', id: 'media-1' }} />)
    const user = userEvent.setup()

    const field = await screen.findByRole('textbox', { name: 'Kommentieren …' })
    await user.type(field, 'Schön, @bo')
    const offered = await screen.findByRole('listbox', { name: 'Personen' })
    expect(within(offered).getAllByRole('option')).toHaveLength(1)
    await user.keyboard('{Enter}')
    expect(field).toHaveValue('Schön, @boris ')

    await user.type(field, 'guck mal{Enter}')

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
        body: 'Schön, @boris guck mal',
      })
    })
  })
})

describe('SocialRail', () => {
  it('asks in a dialog before a comment is deleted', async () => {
    const { calls } = stubApi({
      [COMMENTS]: {
        body: { count: 1, items: [aComment('c1', 'Weg damit', 'Anna', { can_delete: true })] },
      },
      [PEOPLE]: { body: [] },
      'DELETE /api/v1/comments/c1': { status: 204 },
    })
    await renderScreen(<CommentsSection target={{ kind: 'media', id: 'media-1' }} />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Löschen' }))
    const dialog = await screen.findByRole('dialog', { name: 'Diesen Kommentar löschen?' })
    await user.click(within(dialog).getByRole('button', { name: 'Abbrechen' }))
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Löschen' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Löschen' }),
    )
    await waitFor(() => {
      expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
    })
  })

  it('opens the conversation from the speech bubble and shows the numbers', async () => {
    stubApi({
      'GET /api/v1/media/media-1/social': {
        body: {
          likes: 3,
          liked: true,
          likers: ['Boris'],
          favorite: false,
          comments: 2,
          reaction: 'heart',
          reactions: [{ reaction: 'heart', count: 3 }],
          people: [{ name: 'Boris', reaction: 'heart' }],
        },
      },
    })
    const onComments = vi.fn()
    await renderScreen(
      <SocialRail
        target={{ kind: 'media', id: 'media-1' }}
        shifted={false}
        onComments={onComments}
      />,
    )

    const heart = await screen.findByRole('button', { name: 'Gefällt mir nicht mehr' })
    expect(heart).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Kommentare' }))
    expect(onComments).toHaveBeenCalled()
  })
})
