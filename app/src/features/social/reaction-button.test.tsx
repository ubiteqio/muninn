import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReactionButton } from '@/features/social/reaction-button'
import type { Social } from '@/features/social/use-social'

const NOBODY: Social = {
  likes: 0,
  liked: false,
  likers: [],
  favorite: false,
  comments: 0,
  reaction: null,
  reactions: [],
  people: [],
}

describe('ReactionButton', () => {
  it('gives a heart with a tap', async () => {
    const onReact = vi.fn()
    render(<ReactionButton state={NOBODY} pending={false} onReact={onReact} />)

    await userEvent.click(screen.getByRole('button', { name: 'Gefällt mir' }))

    expect(onReact).toHaveBeenCalledWith('heart')
  })

  it("offers every reaction on a right click, and takes one's own back with a tap", async () => {
    const onReact = vi.fn()
    const mine: Social = {
      ...NOBODY,
      likes: 1,
      liked: true,
      reaction: 'fire',
      reactions: [{ reaction: 'fire', count: 1 }],
    }
    const { rerender } = render(<ReactionButton state={NOBODY} pending={false} onReact={onReact} />)

    fireEvent.contextMenu(screen.getByRole('button', { name: 'Gefällt mir' }))
    await userEvent.click(screen.getByRole('menuitemradio', { name: 'Mit 🤙 reagieren' }))
    expect(onReact).toHaveBeenLastCalledWith('hang_loose')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()

    rerender(<ReactionButton state={mine} pending={false} onReact={onReact} />)
    const button = screen.getByRole('button', { name: 'Gefällt mir nicht mehr' })
    expect(within(button).getByText('🔥')).toBeInTheDocument()
    await userEvent.click(button)
    expect(onReact).toHaveBeenLastCalledWith(null)
  })
})
