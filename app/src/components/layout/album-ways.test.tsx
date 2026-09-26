import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { AlbumWays } from '@/components/layout/album-ways'
import { renderScreen } from '@/test/render'

describe('the two ways into the library', () => {
  it('opens the folders and the Smarts from one place, and says what each one is', async () => {
    await renderScreen(<AlbumWays trigger={<button type="button">Alben</button>} />)

    await userEvent.click(screen.getByRole('button', { name: 'Alben' }))

    const folders = await screen.findByRole('menuitem', { name: /Ordner/ })
    expect(folders).toHaveAttribute('href', '/albums')
    expect(folders).toHaveTextContent('Die Ordner der NAS, so wie sie liegen')

    const smarts = screen.getByRole('menuitem', { name: /Smarts/ })
    expect(smarts).toHaveAttribute('href', '/smarts')
    expect(smarts).toHaveTextContent('Sortiert nach dem, was auf den Bildern ist')
  })
})
