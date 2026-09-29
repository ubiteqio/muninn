import { Map as MapLibre } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { inGerman, plainStyle } from '@/features/map/map-style'
import { prepareMapLibre } from '@/features/map/maplibre'
import { useMapStyle } from '@/features/map/use-map'

export interface Point {
  lat: number
  lon: number
  name?: string
  land?: string
  anzahl?: number
}

/**
 * The map on a page of a book: the same basemap as Midgard, drawn to be read on paper.
 *
 * Two of them appear. Behind a page it is a faint street plan under the photographs, and at the
 * end of a book it is the whole journey, with a dashed line from place to place. Neither is
 * meant to be panned - a book is not a map screen - so both are still.
 */
export function BookMap({
  points,
  whole,
  className,
}: {
  points: Point[]
  /** True for the map that closes a book: bigger pins, the place names, room around it. */
  whole?: boolean
  className?: string
}) {
  const element = useRef<HTMLDivElement>(null)
  const style = useMapStyle(false)
  const ready = style.data

  useEffect(() => {
    if (element.current === null || points.length === 0) return
    prepareMapLibre()

    const shown = whole ? heartland(points) : points
    const map = new MapLibre({
      container: element.current,
      style: ready ? inGerman(ready) : plainStyle(false),
      attributionControl: { compact: true },
      interactive: false,
      dragRotate: false,
      ...camera(shown, whole ?? false),
    })

    map.on('load', () => {
      hideForeignNames(map)
      drawRoute(map, points, whole ?? false)
    })

    // A book builds every page and shows one. A map born on a page that is not on screen
    // measures nothing, asks for no tiles and stays empty for ever - it has no reason to look
    // again. This tells it the moment its page has a size.
    const watching = new ResizeObserver(() => {
      map.resize()
    })
    watching.observe(element.current)

    return () => {
      watching.disconnect()
      map.remove()
    }
  }, [points, whole, ready])

  if (points.length === 0) return null
  return <div ref={element} className={className} aria-hidden="true" />
}

function camera(points: Point[], whole: boolean) {
  const only = points[0]
  if (points.length === 1 && only) {
    return { center: [only.lon, only.lat] as [number, number], zoom: 14 }
  }
  const lats = points.map((point) => point.lat)
  const lons = points.map((point) => point.lon)
  return {
    bounds: [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ] as [[number, number], [number, number]],
    fitBoundsOptions: { padding: whole ? 60 : 30, animate: false },
  }
}

/**
 * The places the journey was actually about: the country most of the pictures come from.
 *
 * The airport at home belongs on the line - it is where the journey started - but not in the
 * frame: fitting to it shows all of Europe and none of the holiday. So the map fits the country
 * where the pictures were taken, and the way there runs off the edge.
 */
function heartland(points: Point[]): Point[] {
  const counted = new Map<string, number>()
  for (const point of points) {
    counted.set(point.land ?? '', (counted.get(point.land ?? '') ?? 0) + (point.anzahl ?? 1))
  }
  const [main] = [...counted.entries()].sort((one, other) => other[1] - one[1])[0] ?? ['']
  const there = points.filter((point) => (point.land ?? '') === main)
  return there.length > 1 ? there : points
}

/**
 * The basemap knows the places by their own names, the library by the ones in the gazetteer:
 * Pernau, not Pärnu. Two sets of labels on top of each other read as a mistake, so the map's own
 * settlement names give way. Countries, regions and streets stay - they give the page texture.
 */
function hideForeignNames(map: MapLibre): void {
  for (const layer of map.getStyle().layers) {
    const place = layer.type === 'symbol' && layer['source-layer'] === 'place'
    if (place && !/country|continent|state/.test(layer.id)) {
      map.setLayoutProperty(layer.id, 'visibility', 'none')
    }
  }
}

function drawRoute(map: MapLibre, points: Point[], whole: boolean): void {
  map.addSource('weg', {
    type: 'geojson',
    data: {
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: points.map((one) => [one.lon, one.lat]) },
    },
  })
  if (points.length > 1) {
    map.addLayer({
      id: 'weg',
      type: 'line',
      source: 'weg',
      paint: {
        'line-color': '#1c2740',
        'line-width': 1.6,
        'line-dasharray': [2.4, 1.8],
        'line-opacity': 0.8,
      },
    })
  }

  map.addSource('orte', {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: points.map((one) => ({
        type: 'Feature' as const,
        properties: { name: one.name ?? '', anzahl: one.anzahl ?? 1 },
        geometry: { type: 'Point' as const, coordinates: [one.lon, one.lat] },
      })),
    },
  })
  map.addLayer({
    id: 'orte',
    type: 'circle',
    source: 'orte',
    paint: {
      'circle-radius': whole
        ? ['interpolate', ['linear'], ['get', 'anzahl'], 1, 4.5, 40, 9]
        : 3,
      'circle-color': '#b7791f',
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#fdfaf2',
    },
  })
  if (!whole) return

  map.addLayer({
    id: 'namen',
    type: 'symbol',
    source: 'orte',
    filter: ['!=', ['get', 'name'], ''],
    layout: {
      'text-field': ['get', 'name'],
      'text-size': 14,
      'text-radial-offset': 0.9,
      'text-variable-anchor': ['bottom', 'top', 'left', 'right'],
      'text-font': ['Noto Sans Regular'],
      'text-padding': 4,
      // Where several places sit on top of each other, the one the journey spent its time in
      // keeps its name.
      'symbol-sort-key': ['-', 0, ['get', 'anzahl']],
    },
    paint: { 'text-color': '#2b2620', 'text-halo-color': '#fdfaf2', 'text-halo-width': 1.6 },
  })
}
