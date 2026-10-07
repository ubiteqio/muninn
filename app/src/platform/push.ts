import { Capacitor } from '@capacitor/core'
import { PushNotifications } from '@capacitor/push-notifications'

import { api } from '@/api/client'

/** Where a tapped push leads: the picture, else its album, else nowhere in particular. */
export interface PushTarget {
  mediaId?: string
  albumId?: string
}

const TOKEN_KEY = 'muninn.push-token'

let listening = false
let open: ((target: PushTarget) => void) | null = null

/**
 * The bell on the lock screen. Asks once whether Muninn may send notifications, then tells the
 * server which phone this is - on every start, since Apple may hand out a new token and the phone
 * may have changed hands. Only on the iPhone for now: Android needs Firebase first.
 */
export async function startPush(onOpen: (target: PushTarget) => void): Promise<void> {
  if (Capacitor.getPlatform() !== 'ios') return
  open = onOpen

  if (!listening) {
    listening = true
    await PushNotifications.addListener('registration', ({ value }) => {
      remember(value)
      void api.POST('/api/v1/me/devices', { body: { platform: 'ios', token: value } })
    })
    await PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => {
      const data = notification.data as Record<string, unknown>
      open?.({
        ...(typeof data.media_id === 'string' ? { mediaId: data.media_id } : {}),
        ...(typeof data.album_id === 'string' ? { albumId: data.album_id } : {}),
      })
    })
  }

  let permission = await PushNotifications.checkPermissions()
  if (permission.receive === 'prompt' || permission.receive === 'prompt-with-rationale') {
    permission = await PushNotifications.requestPermissions()
  }
  if (permission.receive === 'granted') await PushNotifications.register()
}

/** Before signing out: this phone hears nothing more for the account leaving it. */
export async function stopPush(): Promise<void> {
  if (Capacitor.getPlatform() !== 'ios') return
  const token = remembered()
  if (!token) return
  try {
    await api.DELETE('/api/v1/me/devices/{token}', { params: { path: { token } } })
  } catch {
    // Signed out all the same; the next account to sign in here takes the phone over.
  }
  forget()
}

// The token only matters for saying goodbye; losing it costs one stray push at most.
function remember(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // No storage, no goodbye.
  }
}

function remembered(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function forget() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to forget.
  }
}
