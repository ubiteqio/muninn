import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminAiPage } from '@/features/admin/ai-page'
import { useAuthStore } from '@/features/auth/auth-store'
import { aUser, stubApi } from '@/test/api-stub'
import { renderScreen } from '@/test/render'

const PROFILES = 'GET /api/v1/admin/ai/profiles'

const gpu = {
  id: 'profile-1',
  kind: 'analyzer' as const,
  name: 'GPU im Keller',
  base_url: 'http://gpu.zuhause:8000/v1',
  model: 'Qwen3-VL-8B-Instruct',
  concurrency: 2,
  timeout_seconds: 120,
  is_active: true,
  has_api_key: false,
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

beforeEach(() => {
  useAuthStore.setState({
    status: 'signed-in',
    needsPasswordChange: false,
    user: { ...aUser, role: 'admin' },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the AI area', () => {
  it('names the five interfaces, whether or not a machine is set up', async () => {
    stubApi({ [PROFILES]: { body: [] } })

    await renderScreen(<AdminAiPage />)

    expect(await screen.findByRole('heading', { name: 'Bildvektoren' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Beschreiben' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Textvektoren' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sprache' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Gesichter' })).toBeInTheDocument()
    expect(screen.getAllByText(/Noch keine Maschine eingerichtet/)).toHaveLength(5)
  })

  it('shows a machine with its model, its address and what it is allowed to do', async () => {
    stubApi({ [PROFILES]: { body: [gpu] } })

    await renderScreen(<AdminAiPage />)

    expect(await screen.findByText('GPU im Keller')).toBeInTheDocument()
    expect(
      screen.getByText('Qwen3-VL-8B-Instruct · http://gpu.zuhause:8000/v1'),
    ).toBeInTheDocument()
    expect(screen.getByText(/2 Anfragen gleichzeitig · 120 s Zeitlimit/)).toBeInTheDocument()
    expect(screen.getByText('in Benutzung')).toBeInTheDocument()
  })

  it('repeats what the machine answered when it was asked', async () => {
    stubApi({
      [PROFILES]: { body: [gpu] },
      'POST /api/v1/admin/ai/profiles/profile-1/test': {
        body: {
          ok: true,
          detail: 'Qwen3-VL-8B-Instruct antwortet: „bereit“',
          milliseconds: 412,
          dimensions: null,
        },
      },
    })

    await renderScreen(<AdminAiPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Verbindung testen' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('antwortet: „bereit“')
    })
    expect(screen.getByRole('status')).toHaveTextContent('in 412 ms')
  })

  it('says plainly when nobody answered', async () => {
    stubApi({
      [PROFILES]: { body: [gpu] },
      'POST /api/v1/admin/ai/profiles/profile-1/test': {
        body: {
          ok: false,
          detail: 'Keine Antwort innerhalb von 120 Sekunden.',
          milliseconds: 120_000,
          dimensions: null,
        },
      },
    })

    await renderScreen(<AdminAiPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Verbindung testen' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Keine Antwort')
    })
  })

  it('names the field the server refused, instead of shrugging', async () => {
    stubApi({
      [PROFILES]: { body: [] },
      'POST /api/v1/admin/ai/profiles': {
        problem: {
          type: 'urn:muninn:problem:validation-failed',
          title: 'Request validation failed',
          status: 422,
          errors: [
            {
              location: ['body', 'concurrency'],
              message: 'Input should be greater than or equal to 1',
              type: 'greater_than_equal',
            },
          ],
        },
      },
    })

    await renderScreen(<AdminAiPage />)
    const [addToImages] = await screen.findAllByRole('button', { name: 'Hinzufügen' })
    await userEvent.click(addToImages as HTMLElement)
    await userEvent.type(screen.getByLabelText('Name'), 'GPU')
    await userEvent.type(screen.getByLabelText('Basis-URL'), 'http://gpu:8000/v1')
    await userEvent.type(screen.getByLabelText('Modell'), 'siglip2')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    expect(await screen.findByText('Bitte prüfen: Gleichzeitig.')).toBeInTheDocument()
  })

  it('sets up a machine without making anybody type a secret twice', async () => {
    const { calls } = stubApi({
      [PROFILES]: { body: [] },
      'POST /api/v1/admin/ai/profiles': { status: 201, body: gpu },
    })

    await renderScreen(<AdminAiPage />)
    const [addToImages] = await screen.findAllByRole('button', { name: 'Hinzufügen' })
    await userEvent.click(addToImages as HTMLElement)

    await userEvent.type(screen.getByLabelText('Name'), 'GPU im Keller')
    await userEvent.type(screen.getByLabelText('Basis-URL'), 'http://gpu.zuhause:8000/v1')
    await userEvent.type(screen.getByLabelText('Modell'), 'siglip2')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => {
      expect(calls.some((call) => call.method === 'POST')).toBe(true)
    })
    const sent = calls.find((call) => call.method === 'POST')?.body as Record<string, unknown>
    expect(sent.kind).toBe('image_embedder')
    expect(sent.model).toBe('siglip2')
  })
})
