import { Capacitor } from '@capacitor/core'

/**
 * Where Muninn runs.
 *
 * In a browser that is simply wherever the app was loaded from. The native app is loaded from
 * inside itself, so it has to be told once - the family server has no fixed address that could
 * be baked in. What is stored is an address, not a secret, so it lives in ordinary storage; the
 * tokens have their own place.
 */
const KEY = 'muninn.server'

/** Set at build time for a fleet that always points at the same server. */
const BUILT_IN = (import.meta.env.VITE_SERVER_URL as string | undefined) ?? ''

export function isNative(): boolean {
  return Capacitor.isNativePlatform()
}

export function serverOrigin(): string {
  if (!isNative()) return location.origin

  return stored() ?? BUILT_IN
}

/** True when the native app has nowhere to ask yet, and has to be told first. */
export function needsServerAddress(): boolean {
  return isNative() && serverOrigin() === ''
}

/**
 * Remember the server address, as an origin: what somebody types is a host, maybe with a port,
 * maybe with a path they did not mean to paste.
 */
export function rememberServer(address: string): string {
  const cleaned = address.trim()
  const withScheme = /^https?:\/\//i.test(cleaned) ? cleaned : `${schemeFor(cleaned)}${cleaned}`
  const { origin } = new URL(withScheme)

  try {
    localStorage.setItem(KEY, origin)
  } catch {
    // A device that refuses storage still works for this session.
  }
  return origin
}

export function forgetServer(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Nothing to forget, then.
  }
}

/**
 * Which scheme to assume when somebody types a bare address.
 *
 * A machine in the house is reached by its number or its name in the local network, and it
 * rarely has a certificate - insisting on HTTPS there would simply fail. Anything that looks
 * like a name on the internet gets HTTPS, because that is where a plain connection would be
 * careless.
 */
function schemeFor(address: string): string {
  const host = address.split('/')[0]?.split(':')[0] ?? ''
  const isAddress = /^\d{1,3}(\.\d{1,3}){3}$/.test(host)
  const isLocalName = !host.includes('.') || host.endsWith('.local')

  return isAddress || isLocalName ? 'http://' : 'https://'
}

function stored(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}
