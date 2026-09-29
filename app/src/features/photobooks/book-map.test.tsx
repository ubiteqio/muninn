import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const built: unknown[] = []
const order: string[] = []

vi.mock('maplibre-gl', () => ({
  Map: class {
    constructor(options: unknown) {
      order.push('map')
      built.push(options)
    }
    on() {}
    remove() {}
    getStyle() {
      return { layers: [] }
    }
  },
}))

vi.mock('@/features/map/maplibre', () => ({
  prepareMapLibre: () => {
    order.push('prepare')
  },
}))

// jsdom has no ResizeObserver; the map asks for one to hear when its page gets a size.
class Watcher {
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', Watcher)

vi.mock('@/features/map/use-map', () => ({ useMapStyle: () => ({ data: undefined }) }))

const { BookMap } = await import('@/features/photobooks/book-map')

describe('Die Karte auf einer Buchseite', () => {
  it('says where the worker lies before it builds a map', () => {
    // Without that word MapLibre asks for no tile and says nothing: the page stays empty paper.
    render(<BookMap points={[{ lat: 48.21, lon: 11.62 }]} whole />)

    expect(order).toEqual(['prepare', 'map'])
  })

  it('stays away when the journey has no place', () => {
    const { container } = render(<BookMap points={[]} />)

    expect(container).toBeEmptyDOMElement()
  })
})
