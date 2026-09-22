import '@/index.css'
import '@/i18n'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { applyTheme, storedTheme } from '@/lib/theme'
import { hideNativeSplash } from '@/platform/splash'
import { router } from '@/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Photos and albums change rarely; the WebSocket pushes what does change.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

applyTheme(storedTheme())

// The native launch image stays until somebody says otherwise. This is that somebody.
void hideNativeSplash()

const container = document.getElementById('root')
if (!container) throw new Error('Missing #root element')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
