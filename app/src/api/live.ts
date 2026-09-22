/**
 * The live channel: one WebSocket per tab, shared by whoever wants to listen.
 *
 * Asking again every couple of seconds cannot show work that is over in a tenth of a second, so
 * the server says what happened when it happens. The socket carries the access token as a
 * subprotocol: a browser cannot set headers on a socket, and a token in the address would end up
 * in every proxy log.
 */

import { API_BASE, apiUrl, getAccessToken, refreshSession } from '@/api/session'

export interface LiveEvent {
  topic: string
  at: string
  kind: string
  [field: string]: unknown
}

type Listener = (event: LiveEvent) => void

const TOKEN_PROTOCOL = 'bearer'

/** How long to wait before trying again, growing with each failed attempt. */
const RETRY_MS = [1000, 2000, 5000, 15000]

const listeners = new Set<Listener>()
let socket: WebSocket | null = null
let attempt = 0
let retry: ReturnType<typeof setTimeout> | null = null

function socketUrl(): string {
  const url = new URL(apiUrl(`${API_BASE}/ws`))
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

async function open(): Promise<void> {
  if (socket || listeners.size === 0) return

  // The tab may have been asleep; a socket refused for an expired token would only retry.
  let token = getAccessToken()
  if (!token) {
    try {
      token = await refreshSession()
    } catch {
      return
    }
  }

  const opening = new WebSocket(socketUrl(), [TOKEN_PROTOCOL, token])
  socket = opening

  opening.addEventListener('open', () => {
    attempt = 0
  })

  opening.addEventListener('message', (message: MessageEvent<string>) => {
    let event: LiveEvent
    try {
      event = JSON.parse(message.data) as LiveEvent
    } catch {
      return
    }
    for (const listener of listeners) listener(event)
  })

  opening.addEventListener('close', () => {
    socket = null
    if (listeners.size === 0) return
    const wait = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)] ?? 15000
    attempt += 1
    retry = setTimeout(() => {
      void open()
    }, wait)
  })
}

/**
 * Listen to everything the installation announces. The returned function stops listening, and
 * the socket closes as soon as nobody is left.
 */
export function onLiveEvent(listener: Listener): () => void {
  listeners.add(listener)
  void open()

  return () => {
    listeners.delete(listener)
    if (listeners.size > 0) return
    if (retry) clearTimeout(retry)
    retry = null
    socket?.close()
    socket = null
  }
}
