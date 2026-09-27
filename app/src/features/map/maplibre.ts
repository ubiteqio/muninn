import 'maplibre-gl/dist/maplibre-gl.css'

import { setWorkerUrl } from 'maplibre-gl'
// MapLibre draws in a worker it loads from its own file, which a bundle does not carry along by
// itself: Vite builds it into one file here and MapLibre is told where it lies.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

let told = false

/**
 * What MapLibre needs before the first map is built, wherever that happens.
 *
 * Without the worker file MapLibre asks for no tile at all: the style arrives, the canvas has its
 * size, and the map stays empty for ever without raising a single error. That is what the maps in
 * a photo book did as long as only the map screen said where the worker lies - a book that was
 * opened without passing the map screen showed cream-coloured paper where the journey should be.
 * So everybody who builds a map says this first.
 */
export function prepareMapLibre(): void {
  if (told) return
  setWorkerUrl(workerUrl)
  told = true
}
