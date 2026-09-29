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

  it('offers one try for the row, and says what the others are waiting for', async () => {
    // A stage carries a pause only if it happened to have work while the machine was away.
    // Which of them do says more about what there was to do than about the machine, so the
    // button belongs to the row - and a stage that is merely down says so in words.
    const { calls } = stubApi({
      [HEALTH]: {
        body: {
          services: [
            aService('face_detector', {
              ok: false,
              detail: 'nicht erreichbar',
              paused_until: '2026-09-22T06:46:00Z',
            }),
            aService('text_embedder', { ok: false, detail: 'nicht erreichbar' }),
          ],
        },
      },
      'POST /api/v1/admin/jobs/ai/retry': { body: { services: [] } },
    })

    await renderScreen(<AiServices />)

    const list = await screen.findByRole('list')
    expect(within(list).getByText(/pausiert bis/)).toBeInTheDocument()
    expect(within(list).getByText(/wird beim nächsten Auftrag versucht/)).toBeInTheDocument()
    // One button, and it is not inside a chip.
    expect(within(list).queryByRole('button')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Jetzt versuchen' }))

    await waitFor(() => {
      expect(calls.some((call) => call.path.endsWith('/ai/retry'))).toBe(true)
    })
  })

  it('offers nothing to try while every machine answers', async () => {
    stubApi({
      [HEALTH]: { body: { services: [aService('image_embedder', { ok: true })] } },
    })

    await renderScreen(<AiServices />)

    await screen.findByRole('region', { name: 'KI-Dienste' })
    expect(screen.queryByRole('button', { name: 'Jetzt versuchen' })).not.toBeInTheDocument()
  })
})
