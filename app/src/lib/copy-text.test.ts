import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyText } from '@/lib/copy-text'

describe('copyText', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('copies over plain HTTP, where the browser has no clipboard API', async () => {
    vi.stubGlobal('isSecureContext', false)
    const command = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: command, configurable: true })

    expect(await copyText('k7fp-2m9x-qt4w')).toBe(true)
    expect(command).toHaveBeenCalledWith('copy')
    // The helper field is gone again.
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('says so when nothing could be copied', async () => {
    vi.stubGlobal('isSecureContext', false)
    Object.defineProperty(document, 'execCommand', { value: () => false, configurable: true })

    expect(await copyText('x')).toBe(false)
  })
})
