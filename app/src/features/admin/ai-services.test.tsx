import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AiServices } from '@/features/admin/ai-services'
import { stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const HEALTH = 'GET /api/v1/admin/jobs/ai'

function aService(kind: string, extra: object = {}) {
  return {
    kind,
    configured: true,
    name: kind,
    model: `${kind}-model`,
    ok: true,
    detail: 'antwortet.',
    milliseconds: 38,
    checked_at: new Date().toISOString(),
    paused_until: null,
    ...extra,
  }
}

const OFF = {
  configured: false,
  name: null,
  model: null,
  ok: null,
  detail: null,
  milliseconds: null,
  checked_at: null,
}

describe('AiServices', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows each service green, red or grey, with the time or the reason', async () => {
    stubApi({
      [HEALTH]: {
        body: {
          services: [
            aService('analyzer', {
              ok: false,
              detail: 'http://gpu:8000/v1 ist nicht erreichbar.',
              milliseconds: 3,
              paused_until: '2026-09-22T00:47:00Z',
            }),
            aService('image_embedder', { milliseconds: 4100 }),
            aService('face_detector', OFF),
          ],
        },
      },
    })
    await renderScreen(<AiServices />)

    const list = await screen.findByRole('list')
    const describing = within(list).getByLabelText(/^Beschreiben, antwortet nicht, pausiert bis/)
    expect(describing).toHaveAttribute('title', expect.stringContaining('ist nicht erreichbar'))
    expect(within(describing).getByText('antwortet nicht')).toBeInTheDocument()

    const pictures = within(list).getByLabelText('Bildvektoren, antwortet')
    expect(within(pictures).getByText('4,1 s')).toBeInTheDocument()

    expect(within(list).getByLabelText('Gesichter, nicht eingerichtet')).toBeInTheDocument()
    expect(screen.getByText(/^geprüft vor \d+ s$/)).toBeInTheDocument()
  })

  it('stays out of the way while there is no answer yet', async () => {
    stubApi({ [HEALTH]: { problem: { type: 'about:blank', title: 'Fehler', status: 500 } } })
    await renderScreen(<AiServices />)

    expect(screen.queryByRole('region', { name: 'KI-Dienste' })).not.toBeInTheDocument()
  })

  it('wakes a paused service with a click on its chip', async () => {
    const { calls } = stubApi({
      [HEALTH]: {
        body: {
          services: [
            aService('face_detector', {
              ok: false,
              detail: 'nicht erreichbar',
              paused_until: '2026-09-22T06:46:00Z',
            }),
          ],
        },
      },
      'DELETE /api/v1/admin/jobs/ai/face_detector/pause': { status: 204 },
    })

    await renderScreen(<AiServices />)
    await userEvent.click(
      await screen.findByRole('button', {
        name: /^Gesichter, antwortet nicht, .*Jetzt versuchen$/,
      }),
    )

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'DELETE')).toBe(true)
    })
  })
})
