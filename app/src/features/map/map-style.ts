import type { ExpressionSpecification, LayerSpecification, StyleSpecification } from 'maplibre-gl'

/**
 * The basemap comes from OpenFreeMap: free, without a key, and made for MapLibre. It only
 * learns which part of the map is looked at, never anything about the photos on it.
 */
const STYLES = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
} as const

/** Without the basemap - offline, or the service down - the photos still sit on this. */
export function plainStyle(dark: boolean): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': dark ? '#0B0D12' : '#F5F0E6' },
      },
    ],
  }
}

export async function loadStyle(dark: boolean): Promise<StyleSpecification> {
  const response = await fetch(dark ? STYLES.dark : STYLES.light)
  if (!response.ok) throw new Error(`map style: ${String(response.status)}`)
  return inGerman((await response.json()) as StyleSpecification)
}

/** Place names in German where the map knows them: München, not Munich or Muenchen. */
export function inGerman(style: StyleSpecification): StyleSpecification {
  return { ...style, layers: style.layers.map(germanLabels) }
}

function germanLabels(layer: LayerSpecification): LayerSpecification {
  if (layer.type !== 'symbol' || layer.layout?.['text-field'] === undefined) return layer
  const original = layer.layout['text-field'] as ExpressionSpecification
  if (!JSON.stringify(original).includes('"name')) return layer
  return {
    ...layer,
    layout: { ...layer.layout, 'text-field': ['coalesce', ['get', 'name:de'], original] },
  }
}
