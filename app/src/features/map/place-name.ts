import type { components } from '@/api/generated/schema'

export type Place = components['schemas']['PlaceView']

/**
 * "Florenz, Toskana, Italien". A part that repeats is left out: a city state is its own region,
 * so Hamburg reads "Hamburg, Deutschland".
 */
export function placeName(place: Place): string {
  return placeParts(place).join(', ')
}

/** "Toskana, Italien": what follows the town's own name. */
export function placeContext(place: Place): string {
  return placeParts(place).slice(1).join(', ')
}

function placeParts(place: Place): string[] {
  return [place.name, place.region, place.country].filter(
    (part, index, parts): part is string => !!part && parts.indexOf(part) === index,
  )
}
