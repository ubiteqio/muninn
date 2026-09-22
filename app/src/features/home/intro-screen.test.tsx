import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { IntroScreen } from '@/features/home/intro-screen'

async function renderIntro() {
  const root = createRootRoute({ component: () => <Outlet /> })
  const router = createRouter({
    routeTree: root.addChildren([
      createRoute({ getParentRoute: () => root, path: '/', component: IntroScreen }),
      createRoute({ getParentRoute: () => root, path: '/home', component: () => <p>Home</p> }),
    ]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  await router.load()
  render(<RouterProvider router={router} />)
  return router
}

describe('IntroScreen', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the mark, dissolves and moves on to the start page in its place', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const router = await renderIntro()

    expect(screen.getByText('MUNINN')).toBeInTheDocument()
    expect(screen.queryByText('Home')).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })

    expect(await screen.findByText('Home')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/home')
    // Replaced, not pushed: going back does not show the intro again.
    expect(router.history.length).toBe(1)
  })
})
