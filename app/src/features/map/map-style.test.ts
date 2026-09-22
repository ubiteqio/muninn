import type { StyleSpecification } from 'maplibre-gl'
import { describe, expect, it } from 'vitest'

import { inGerman, plainStyle } from '@/features/map/map-style'

describe('inGerman', () => {
  it('prefers the German name in labels and leaves other layers alone', () => {
    const style: StyleSpecification = {
      version: 8,
      sources: {},
      layers: [
        { id: 'water', type: 'background' },
        { id: 'city', type: 'symbol', source: 'x', layout: { 'text-field': ['get', 'name'] } },
        {
          id: 'road-number',
          type: 'symbol',
          source: 'x',
          layout: { 'text-field': ['get', 'ref'] },
        },
      ],
    }

    const [water, city, road] = inGerman(style).layers

    expect(water).toEqual(style.layers[0])
    expect(city).toMatchObject({
      layout: { 'text-field': ['coalesce', ['get', 'name:de'], ['get', 'name']] },
    })
    expect(road).toEqual(style.layers[2])
  })
})

describe('plainStyle', () => {
  it('is only a background in the colour of the page', () => {
    expect(plainStyle(true).layers).toEqual([
      { id: 'background', type: 'background', paint: { 'background-color': '#0B0D12' } },
    ])
  })
})
