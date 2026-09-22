import { createRootRoute, Outlet } from '@tanstack/react-router'
import { useEffect } from 'react'

import { useAuthStore } from '@/features/auth/auth-store'
import { SessionGate } from '@/features/auth/session-gate'

function Root() {
  const restore = useAuthStore((state) => state.restore)

  // One attempt to restore the session per app start: the refresh token decides.
  useEffect(() => {
    void restore()
  }, [restore])

  return (
    <SessionGate>
      <Outlet />
    </SessionGate>
  )
}

export const Route = createRootRoute({ component: Root })
