import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'

/**
 * Renders a screen inside a router and a query client, which the navigation and any data hooks
 * need. The real route tree is not used: a test names the screen it is about.
 *
 * The screen sits at the path it is opened on, so a screen that writes into its own address -
 * the search opening a picture - stays where it is instead of landing on "Not Found".
 */
export async function renderScreen(ui: ReactNode, { path = '/' }: { path?: string } = {}) {
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const screenRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: new URL(path, 'http://test').pathname,
    component: () => <>{ui}</>,
  })

  const router = createRouter({
    routeTree: rootRoute.addChildren([screenRoute]),
    history: createMemoryHistory({ initialEntries: [path] }),
    // jsdom has no layout, so there is nothing to restore and nothing to scroll.
    scrollRestoration: false,
  })

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  // The router resolves its first match before anything renders.
  await router.load()

  // The router comes back too: a screen that navigates somewhere is tested by where it went.
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
    router,
  }
}
