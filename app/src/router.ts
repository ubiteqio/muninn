import { createRouter, parseSearchWith, stringifySearchWith } from '@tanstack/react-router'

import { Route as rootRoute } from '@/routes/__root'
import {
  adminAiRoute,
  adminDuplicatesRoute,
  adminFoldersRoute,
  adminJobsRoute,
  adminRoute,
  adminSettingsRoute,
  adminUsersRoute,
  albumRoute,
  albumsRoute,
  chapterRoute,
  favoritesRoute,
  homeRoute,
  introRoute,
  mapRoute,
  overviewRoute,
  peopleRoute,
  personRoute,
  profileRoute,
  searchRoute,
  smartsRoute,
  startRoute,
} from '@/routes/index'

/**
 * Routes are declared by hand. Signing in is not a route: the session gate above the router
 * decides whether any of these can be reached at all.
 */
const routeTree = rootRoute.addChildren([
  introRoute,
  homeRoute,
  startRoute,
  albumsRoute,
  albumRoute,
  smartsRoute,
  chapterRoute,
  favoritesRoute,
  searchRoute,
  mapRoute,
  peopleRoute,
  personRoute,
  profileRoute,
  adminRoute,
  adminAiRoute,
  adminFoldersRoute,
  adminJobsRoute,
  adminSettingsRoute,
  adminUsersRoute,
  adminDuplicatesRoute,
  overviewRoute,
])

/**
 * Search values are plain text in the address.
 *
 * The default runs every value through JSON, which writes `?at="2014"` with the quotes in it.
 * Muninn's search values are all short words - a level, a month, an id - and an address is
 * something people read and send to each other.
 */
export const router = createRouter({
  routeTree,
  parseSearch: parseSearchWith((value) => value),
  stringifySearch: stringifySearchWith((value: unknown) =>
    typeof value === 'string' ? value : JSON.stringify(value),
  ),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
