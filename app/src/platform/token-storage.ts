import { SecureStorage } from '@aparajita/capacitor-secure-storage'
import { Capacitor } from '@capacitor/core'

/**
 * Where the refresh token lives, which differs by platform.
 *
 * In the browser the server sets it as an httpOnly cookie: JavaScript cannot read it, which is the
 * point, so the web adapter stores nothing and the browser sends it by itself. The native app uses
 * no cookies at all and has to keep the token itself.
 */
export interface TokenStorage {
  readonly kind: 'web' | 'native'
  read(): Promise<string | null>
  write(token: string): Promise<void>
  clear(): Promise<void>
}

const webStorage: TokenStorage = {
  kind: 'web',
  read: () => Promise.resolve(null),
  write: () => Promise.resolve(),
  clear: () => Promise.resolve(),
}

/** One key, in the Keychain on iOS and the Keystore-backed store on Android. */
const KEY = 'refresh-token'

/**
 * The concept asks for the Keychain and the Keystore, and this is what reaches them.
 *
 * A device that refuses - a Keychain that is locked, a device without a screen lock - must not
 * take the app down with it: the session is then simply not remembered, and whoever uses it
 * signs in again.
 */
const nativeStorage: TokenStorage = {
  kind: 'native',

  read: async () => {
    try {
      const value = await SecureStorage.get(KEY)
      return typeof value === 'string' ? value : null
    } catch {
      return null
    }
  },

  write: async (token: string) => {
    try {
      await SecureStorage.set(KEY, token)
    } catch {
      // Not remembered is better than not working.
    }
  },

  clear: async () => {
    try {
      await SecureStorage.remove(KEY)
    } catch {
      // Nothing to clear, then.
    }
  },
}

export const tokenStorage: TokenStorage = Capacitor.isNativePlatform() ? nativeStorage : webStorage
