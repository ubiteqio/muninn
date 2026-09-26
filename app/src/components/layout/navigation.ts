import { useAuthStore } from '@/features/auth/auth-store'

/** The five destinations of the app, in the order the design shows them. */
export const NAVIGATION = [
  { id: 'home', icon: 'home', to: '/home' },
  { id: 'albums', icon: 'photo_library', to: '/albums' },
  { id: 'search', icon: 'search', to: '/search' },
  { id: 'map', icon: 'map', to: '/map' },
  { id: 'profile', icon: 'person', to: '/profile' },
] as const

/**
 * What "Alben" opens: the folders as they lie on the NAS, and the Smarts - the same media
 * sorted by what is in them. Both are ways into the library, so they hang on one destination
 * rather than taking two places in a rail that has five.
 */
export const ALBUM_WAYS = [
  { id: 'folders', icon: 'folder', to: '/albums' },
  { id: 'smarts', icon: 'auto_awesome', to: '/smarts' },
] as const

/** Personen: after the map in the rail, and in the phone's bottom bar. */
export const PEOPLE_DESTINATION = { id: 'people', icon: 'group', to: '/people' } as const

/** Überblick, the library at a glance - in the rail after Personen, under "Mehr" on the phone. */
export const OVERVIEW_DESTINATION = { id: 'overview', icon: 'bar_chart', to: '/overview' } as const

/**
 * The phone's bottom bar: Alben, Karte, Home in the middle, Personen - and "Mehr" at the right
 * edge, which opens Überblick and Profil. Five equal places; the search sits up beside the bell.
 */
export const MOBILE_NAVIGATION = [
  NAVIGATION[1],
  NAVIGATION[3],
  NAVIGATION[0],
  PEOPLE_DESTINATION,
] as const

/** What "Mehr" opens on the phone, in this order. */
export const MOBILE_MORE = [OVERVIEW_DESTINATION, NAVIGATION[4]] as const

/** What the rail puts under "Mehr" where it is too short for everything: the rest, in order. */
export function moreOf(all: readonly NavigationItem[]): readonly NavigationItem[] {
  const shown = new Set<string>(MOBILE_NAVIGATION.map((item) => item.id))
  return all.filter((item) => !shown.has(item.id))
}

/** Hliðskjálf, the sixth destination. Only admins have it, and only they may open it. */
export const ADMIN_DESTINATION = { id: 'admin', icon: 'shield_person', to: '/admin' } as const

export type NavigationItem =
  | (typeof NAVIGATION)[number]
  | typeof PEOPLE_DESTINATION
  | typeof OVERVIEW_DESTINATION
  | typeof ADMIN_DESTINATION

/** The sidebar's destinations: Start, Alben, Karte, Personen, Überblick, Profil, and Admin for
 * admins. */
export function useNavigation(): readonly NavigationItem[] {
  const isAdmin = useAuthStore((state) => state.user?.role === 'admin')
  // The search lives in the header beside its field ("Erweitert"), not in the rail.
  const [home, albums, , map, profile] = NAVIGATION
  const rail = [home, albums, map, PEOPLE_DESTINATION, OVERVIEW_DESTINATION, profile]

  return isAdmin ? [...rail, ADMIN_DESTINATION] : rail
}
