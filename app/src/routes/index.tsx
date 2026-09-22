import { createRoute, lazyRouteComponent, Navigate } from '@tanstack/react-router'

import { AdminAiPage } from '@/features/admin/ai-page'
import { AdminDuplicatesPage } from '@/features/admin/duplicates-page'
import { AdminFoldersPage } from '@/features/admin/folders-page'
import { AdminJobsPage } from '@/features/admin/jobs-page'
import { AdminSettingsPage } from '@/features/admin/settings-page'
import { AdminUsersPage } from '@/features/admin/users-page'
import { AlbumsScreen } from '@/features/albums/albums-screen'
import { HomeScreen } from '@/features/home/home-screen'
import { IntroScreen } from '@/features/home/intro-screen'
import { OverviewScreen } from '@/features/overview/overview-screen'
import { PeopleScreen,type PeopleSearch } from '@/features/people/people-screen'
import { PersonScreen } from '@/features/people/person-screen'
import { ProfileScreen } from '@/features/profile/profile-screen'
import { SearchScreen } from '@/features/search/search-screen'
import { WalhallScreen } from '@/features/social/walhall-screen'
import { Route as rootRoute } from '@/routes/__root'

/**
 * One search value as text.
 *
 * A query string has no types, and whoever reads it has to pick one: "2014" arrives as the
 * number 2014, "2014-08" as a string. Everything Muninn puts in an address is text - a level, a
 * month, an id - so that is what comes back out, whatever it looked like on the way.
 */
function asText(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

/**
 * What the start screen is showing: which distance the timeline is looked at from, which year
 * or month, and whether a medium is open. All three in the address, so a level can be sent to
 * somebody and the back button steps out of it.
 */
export interface HomeSearch {
  view?: 'years' | 'months' | 'days'
  at?: string
  medium?: string
}

function validateHomeSearch(search: Record<string, unknown>): HomeSearch {
  const at = asText(search.at)
  const medium = asText(search.medium)
  return {
    ...(search.view === 'years' || search.view === 'months' || search.view === 'days'
      ? { view: search.view }
      : {}),
    ...(at === undefined ? {} : { at }),
    ...(medium === undefined ? {} : { medium }),
  }
}

/**
 * The bare address: the mark as an intro, then the start page. An address that already says
 * what to show - an older link to a picture on the start page - goes there at once.
 */
export const introRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: IntroRoute,
  validateSearch: validateHomeSearch,
})

function IntroRoute() {
  const search = introRoute.useSearch()
  if (Object.keys(search).length > 0) return <Navigate to="/home" search={search} replace />
  return <IntroScreen />
}

export const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/home',
  component: HomeRoute,
  validateSearch: validateHomeSearch,
})

/**
 * The start page's old address. Bookmarks, links sent around and the phone app's last place
 * still say /start; they arrive at /home with everything they asked for.
 */
export const startRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/start',
  validateSearch: validateHomeSearch,
  component: StartRoute,
})

function StartRoute() {
  return <Navigate to="/home" search={startRoute.useSearch()} replace />
}

function HomeRoute() {
  const { view, at, medium } = homeRoute.useSearch()
  return <HomeScreen view={view} at={at} medium={medium} />
}

export const profileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/profile',
  component: ProfileScreen,
})

/**
 * Hliðskjálf, the admin area: a sixth destination that only admins see. Its own address has no
 * page of its own and opens the settings, which is where an admin comes to change something.
 */
export const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin',
  component: () => <Navigate to="/admin/settings" replace />,
})

export const adminSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/settings',
  component: AdminSettingsPage,
})

export const adminFoldersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/folders',
  component: AdminFoldersPage,
})

export const adminJobsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/jobs',
  component: AdminJobsPage,
})

export const adminAiRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/ai',
  component: AdminAiPage,
})

export const adminUsersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/users',
  component: AdminUsersPage,
})

/** Überblick: the library at a glance, for everybody. */
export const overviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/overview',
  component: OverviewScreen,
})

export const adminDuplicatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin/duplicates',
  component: AdminDuplicatesPage,
})

/** Yggdrasil: the tree itself, and one album inside it. */
export const albumsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/albums',
  component: () => <AlbumsScreen />,
})

/**
 * Which page of the album is on screen stands in the address, so a link leads a friend to the
 * same pictures. A cursor rather than a page number: it holds on to one medium, whatever is
 * added elsewhere in the album, and page numbers get slow on a table of this size.
 */
export interface AlbumSearch {
  /** The page after this medium. */
  cursor?: string
  /** The page in front of this medium. */
  before?: string
  /** The medium shown full screen. In the address, so a picture can be linked to. */
  medium?: string
}

export const albumRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/albums/$albumId',
  component: AlbumRoute,
  validateSearch: (search: Record<string, unknown>): AlbumSearch => {
    const cursor = asText(search.cursor)
    const before = asText(search.before)
    const medium = asText(search.medium)
    return {
      ...(cursor === undefined ? {} : { cursor }),
      ...(before === undefined ? {} : { before }),
      ...(medium === undefined ? {} : { medium }),
    }
  },
})

function AlbumRoute() {
  const { albumId } = albumRoute.useParams()
  const { cursor, before, medium } = albumRoute.useSearch()
  return <AlbumsScreen albumId={albumId} cursor={cursor} before={before} medium={medium} />
}

/** What a search is made of. All of it in the address, so it can be sent and gone back to. */
export interface SearchParams {
  q?: string
  kind?: 'image' | 'video'
  sort?: 'relevance' | 'date'
  /** Pictures like this medium, instead of words. */
  similar?: string
  medium?: string
}

/** Mímir, the search. */
export const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: SearchRoute,
  validateSearch: (search: Record<string, unknown>): SearchParams => {
    const q = asText(search.q)
    const similar = asText(search.similar)
    const medium = asText(search.medium)
    return {
      ...(q === undefined ? {} : { q }),
      ...(search.kind === 'image' || search.kind === 'video' ? { kind: search.kind } : {}),
      ...(search.sort === 'date' ? { sort: 'date' as const } : {}),
      ...(similar === undefined ? {} : { similar }),
      ...(medium === undefined ? {} : { medium }),
    }
  },
})

function SearchRoute() {
  return <SearchScreen {...searchRoute.useSearch()} />
}

/** Personen: naming faces and looking after persons. Reached from the search. */
export const peopleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/people',
  component: PeopleRoute,
  validateSearch: (search: Record<string, unknown>): PeopleSearch => {
    const letter = asText(search.letter)
    const page = Number(search.page)
    return {
      ...(letter !== undefined && /^[A-Z#]$/.test(letter) ? { letter } : {}),
      ...(Number.isInteger(page) && page > 1 ? { page } : {}),
    }
  },
})

function PeopleRoute() {
  return <PeopleScreen {...peopleRoute.useSearch()} />
}

export const personRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/people/$personId',
  component: PersonRoute,
})

function PersonRoute() {
  const { personId } = personRoute.useParams()
  return <PersonScreen key={personId} personId={personId} />
}

/** Walhall: everybody's own favourites. */
export const favoritesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/favorites',
  component: FavoritesRoute,
  validateSearch: (search: Record<string, unknown>): { medium?: string } => {
    const medium = asText(search.medium)
    return medium === undefined ? {} : { medium }
  },
})

function FavoritesRoute() {
  const { medium } = favoritesRoute.useSearch()
  return <WalhallScreen medium={medium} />
}

/** The map brings MapLibre, about a megabyte: it is only loaded when somebody opens the map. */
export const mapRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/map',
  component: lazyRouteComponent(() => import('@/features/map/map-screen'), 'MapScreen'),
})
