import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WalhallScreen } from '@/features/social/walhall-screen'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

describe('WalhallScreen', () => {
  it('says how it fills before anything is kept', async () => {
    stubApi({
      'GET /api/v1/favorites/albums': { body: [] },
      'GET /api/v1/favorites/media': { body: { items: [], next_cursor: null } },
    })

    await renderScreen(<WalhallScreen />)

    expect(
      await screen.findByText(/Tippe bei einem Bild oder Album auf den Stern/),
    ).toBeInTheDocument()
  })
})
