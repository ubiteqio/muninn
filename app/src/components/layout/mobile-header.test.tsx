import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { MobileHeader } from '@/components/layout/mobile-header'
import { MobileNav } from '@/components/layout/mobile-nav'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function signedInAs(role: 'user' | 'admin') {
  useAuthStore.setState({
    status: 'signed-in',
    user: { ...aUser, role },
    needsPasswordChange: false,
  })
}

beforeEach(() => {
  stubApi({})
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the phone layout', () => {
  it('sends an admin into the admin area through the own avatar', async () => {
    signedInAs('admin')

    await renderScreen(<MobileHeader />)

    expect(screen.getByRole('link', { name: 'Admin öffnen' })).toHaveAttribute('href', '/admin')
  })

  it('offers a plain user no way in', async () => {
    signedInAs('user')

    await renderScreen(<MobileHeader />)

    expect(screen.queryByRole('link', { name: 'Admin öffnen' })).not.toBeInTheDocument()
  })

  it('keeps the bottom bar at five places, even for an admin', async () => {
    signedInAs('admin')

    await renderScreen(<MobileNav active="home" />)

    const bar = within(screen.getByRole('navigation'))
    // In this order: the links found by name are the bar's links, one after another. "Alben"
    // is not among them - it opens the two ways in, the folders and the Smarts.
    const names = ['Karte', 'Home', 'Personen']
    expect(names.map((name) => bar.getByRole('link', { name }))).toEqual(bar.getAllByRole('link'))
    expect(bar.getByRole('button', { name: 'Alben' })).toBeInTheDocument()
    expect(bar.getByRole('button', { name: 'Mehr' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('opens Überblick and Profil from "Mehr", and marks it while one of them is open', async () => {
    signedInAs('user')
    const user = userEvent.setup()

    await renderScreen(<MobileNav active="overview" />)

    const more = screen.getByRole('button', { name: 'Mehr' })
    expect(more).toHaveClass('text-primary')
    more.focus()
    await user.keyboard('{Enter}')
    const menu = await screen.findByRole('menu')
    const items = ['Überblick', 'Profil'].map((name) =>
      within(menu).getByRole('menuitem', { name }),
    )
    expect(items).toEqual(within(menu).getAllByRole('menuitem'))
    expect(within(menu).getByRole('menuitem', { name: 'Profil' })).toHaveAttribute(
      'href',
      '/profile',
    )
  })
})
