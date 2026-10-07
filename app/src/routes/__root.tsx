import { createRootRoute, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'

import { useAuthStore } from '@/features/auth/auth-store'
import { SessionGate } from '@/features/auth/session-gate'
import { startPush } from '@/platform/push'

function Root() {
  const restore = useAuthStore((state) => state.restore)
  const signedIn = useAuthStore(
    (state) => state.status === 'signed-in' && !state.needsPasswordChange,
  )
  const navigate = useNavigate()

  // One attempt to restore the session per app start: the refresh token decides.
  useEffect(() => {
    void restore()
  }, [restore])

  // Signed in on a phone: the bell may reach the lock screen. A tapped push opens its picture.
  useEffect(() => {
    if (!signedIn) return
    void startPush(({ mediaId, albumId }) => {
      if (albumId) {
        void navigate({
          to: '/albums/$albumId',
          params: { albumId },
          search: mediaId ? { medium: mediaId } : {},
        })
      } else {
        void navigate({ to: '/home' })
      }
    })
  }, [signedIn, navigate])

  return (
    <SessionGate>
      <Outlet />
    </SessionGate>
  )
}

export const Route = createRootRoute({ component: Root })
