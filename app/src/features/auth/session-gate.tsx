import type { ReactNode } from 'react'

import { useAuthStore } from '@/features/auth/auth-store'
import { LoginScreen } from '@/features/auth/login-screen'
import { PasswordScreen } from '@/features/auth/password-screen'
import { SplashScreen } from '@/features/auth/splash-screen'

/**
 * Decides which of three things the app is: starting up, signed out, or in use.
 *
 * The gate sits above the router rather than guarding each route, because the answer does not
 * depend on the route: while the starting password is in place the API refuses everything except
 * the own account, so there is genuinely nowhere else to be.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const status = useAuthStore((state) => state.status)
  const needsPasswordChange = useAuthStore((state) => state.needsPasswordChange)

  if (status === 'unknown' || status === 'restoring') return <SplashScreen />
  if (status === 'signed-out') return <LoginScreen />
  if (needsPasswordChange) return <PasswordScreen />

  return <>{children}</>
}
