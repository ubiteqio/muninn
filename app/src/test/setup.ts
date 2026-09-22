import '@testing-library/jest-dom/vitest'
import '@/i18n'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

/**
 * jsdom implements neither of these, and the start screen needs both: the layout asks for the
 * breakpoint, the timeline watches which date group is on screen. The stubs report "not matching"
 * and "never intersecting", which is the mobile layout in a window of unknown size.
 */
class MediaQueryListStub implements Partial<MediaQueryList> {
  readonly matches = false
  readonly media: string

  constructor(media: string) {
    this.media = media
  }

  addEventListener() {}
  removeEventListener() {}
  dispatchEvent() {
    return false
  }
}

class IntersectionObserverStub implements Partial<IntersectionObserver> {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

/*
 * Defined on the window rather than with vi.stubGlobal: a test that stubs fetch and then calls
 * vi.unstubAllGlobals() would otherwise take these with it and break every later test in the file.
 */
define('matchMedia', (query: string) => new MediaQueryListStub(query))
define('IntersectionObserver', IntersectionObserverStub)

// jsdom has no layout, so scrolling is a no-op instead of a notice on every router mount.
define('scrollTo', () => undefined)

function define(name: string, value: unknown): void {
  Object.defineProperty(window, name, { value, writable: true, configurable: true })
}

// jsdom lays nothing out, so it has nothing to scroll to either.
Element.prototype.scrollIntoView = function scrollIntoView() {}
