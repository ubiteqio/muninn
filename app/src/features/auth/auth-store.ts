import { create } from 'zustand'

import { api, unwrap } from '@/api/client'
import type { components } from '@/api/generated/schema'
import { ApiError } from '@/api/problem'
import {
  forgetTokens,
  onSessionEnded,
  refreshSession,
  rememberTokens,
  SessionExpiredError,
} from '@/api/session'
import { needsServerAddress } from '@/platform/server'
import { tokenStorage } from '@/platform/token-storage'

export type UserProfile = components['schemas']['UserProfile']

/**
 * - `unknown`: the app has just started and has not tried to restore a session yet
 * - `restoring`: a refresh is in flight
 * - `signed-out` / `signed-in`: settled
 */
export type SessionStatus = 'unknown' | 'restoring' | 'signed-out' | 'signed-in'

interface AuthState {
  status: SessionStatus
  user: UserProfile | null
  /** True while the starting password an admin handed out is still in place. */
  needsPasswordChange: boolean

  restore: () => Promise<void>
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  setPassword: (currentPassword: string, newPassword: string) => Promise<void>
}

/** What fetch throws when there is no answer at all: no network, wrong address, server down. */
function isOffline(error: unknown): boolean {
  return error instanceof TypeError
}

/** Browsers send the refresh token as a cookie; the native app puts it in the body. */
const clientKind = tokenStorage.kind === 'native' ? 'native' : 'web'

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'unknown',
  user: null,
  needsPasswordChange: false,

  async restore() {
    if (get().status === 'restoring') return

    // A phone that has not been told where Muninn runs has nobody to ask. Asking anyway would
    // fail slowly and leave the app on its splash screen; the login screen is where the address
    // is entered, so that is where to go.
    if (needsServerAddress()) {
      set({ status: 'signed-out', user: null, needsPasswordChange: false })
      return
    }

    set({ status: 'restoring' })

    try {
      await refreshSession()
      const user = await unwrap(await api.GET('/api/v1/me'))
      set({ status: 'signed-in', user, needsPasswordChange: user.must_change_password })
    } catch (error) {
      set({ status: 'signed-out', user: null, needsPasswordChange: false })

      // Expired, refused, or nobody there at all - all three mean "not signed in". Anything
      // else is a fault in the app itself and has no business being swallowed here.
      const expected =
        error instanceof SessionExpiredError || error instanceof ApiError || isOffline(error)
      if (!expected) throw error
    }
  },

  async signIn(username, password) {
    const tokens = await unwrap(
      await api.POST('/api/v1/auth/login', { body: { username, password, client: clientKind } }),
    )

    await rememberTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    })
    set({
      status: 'signed-in',
      user: tokens.user,
      needsPasswordChange: tokens.user.must_change_password,
    })
  },

  async signOut() {
    try {
      await api.POST('/api/v1/auth/logout', { body: { refresh_token: null } })
    } finally {
      // Whatever the server said, this device is signed out.
      await forgetTokens()
      set({ status: 'signed-out', user: null, needsPasswordChange: false })
    }
  },

  async setPassword(currentPassword, newPassword) {
    const tokens = await unwrap(
      await api.POST('/api/v1/auth/password', {
        body: {
          current_password: currentPassword,
          new_password: newPassword,
          client: clientKind,
        },
      }),
    )

    // Every other device is signed out; this one carries on with a fresh token family.
    await rememberTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    })
    set({ status: 'signed-in', user: tokens.user, needsPasswordChange: false })
  },
}))

/** A refresh that fails mid-session drops the app back to the login screen. */
onSessionEnded(() => {
  useAuthStore.setState({ status: 'signed-out', user: null, needsPasswordChange: false })
})
