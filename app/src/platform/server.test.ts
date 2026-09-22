import { beforeEach, describe, expect, it } from 'vitest'

import { forgetServer, rememberServer } from '@/platform/server'

describe('the server address', () => {
  beforeEach(() => {
    forgetServer()
  })

  it('assumes plain HTTP for a machine in the house', () => {
    // A number in the local network, with a port. It has no certificate, and insisting on one
    // would only fail.
    expect(rememberServer('192.168.178.4:9090')).toBe('http://192.168.178.4:9090')
    expect(rememberServer('muninn:9090')).toBe('http://muninn:9090')
    expect(rememberServer('muninn.local')).toBe('http://muninn.local')
  })

  it('assumes HTTPS for a name on the internet', () => {
    expect(rememberServer('muninn.example.de')).toBe('https://muninn.example.de')
  })

  it('keeps a scheme somebody typed out', () => {
    expect(rememberServer('https://192.168.178.4:9090')).toBe('https://192.168.178.4:9090')
  })

  it('throws away a path that came along with it', () => {
    expect(rememberServer('  http://muninn.local:9090/albums  ')).toBe('http://muninn.local:9090')
  })
})
