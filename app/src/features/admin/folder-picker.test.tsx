import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { FolderPicker } from '@/features/admin/folder-picker'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

function aFolder(name: string, extra: object = {}) {
  return {
    name,
    path: `/library/Events/${name}`,
    relative_path: `Events/${name}`,
    is_mount: false,
    published: true,
    excluded: false,
    publication_id: 'pub-1',
    is_publication: false,
    media_files: null,
    ...extra,
  }
}

describe('FolderPicker inside a published folder', () => {
  it('switches a subfolder off with its switch', async () => {
    const { calls } = stubApi({
      'GET /api/v1/admin/library/browse': {
        body: {
          relative_path: 'Events',
          library_path: '/library',
          current: aFolder('Events', {
            relative_path: 'Events',
            path: '/library/Events',
            is_publication: true,
            media_files: 0,
          }),
          items: [aFolder('FCB'), aFolder('Hochzeit', { published: false, excluded: true })],
        },
      },
      'POST /api/v1/admin/library/publications/pub-1/exclusions': {
        body: { id: 'pub-1', excluded_paths: ['Events/FCB'] },
      },
    })
    const user = userEvent.setup()

    await renderScreen(
      <FolderPicker
        enabled
        initialPath="Events"
        chooseLabel="Veröffentlichen"
        onChoose={vi.fn()}
      />,
    )

    const fcb = await screen.findByRole('switch', { name: 'FCB veröffentlicht' })
    expect(fcb).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('switch', { name: 'Hochzeit veröffentlicht' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    await user.click(fcb)

    await waitFor(() => {
      expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
        relative_path: 'Events/FCB',
      })
    })
  })
})
