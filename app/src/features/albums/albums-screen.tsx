import { Link, useNavigate } from '@tanstack/react-router'
import type { TFunction } from 'i18next'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { useScrollContainer } from '@/components/layout/scroll-container'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AlbumPlace } from '@/features/albums/album-place'
import { EmptyAlbum, EmptyLibrary } from '@/features/albums/empty-library'
import {
  type Album,
  pathTo,
  useAlbumMedia,
  useAlbumSync,
  useAlbumTree,
} from '@/features/albums/use-albums'
import { useLibraryUpdates } from '@/features/albums/use-library-updates'
import { MediaGrid } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { AlbumSocial } from '@/features/social/album-social'
import { useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import type { AlbumSearch } from '@/routes'

interface AlbumsScreenProps {
  albumId?: string
  /** The page of media to show, as it stands in the address. */
  cursor?: string | undefined
  before?: string | undefined
  /** The medium shown full screen, likewise from the address. */
  medium?: string | undefined
}

/**
 * Yggdrasil: the folders of the NAS as a tree one can walk through.
 *
 * The whole tree is fetched once, so the path, the subalbums and the titles are lookups. Of the
 * album one is looking at, only the page of media the address asks for is fetched.
 */
export function AlbumsScreen({ albumId, cursor, before, medium }: AlbumsScreenProps) {
  const { t } = useTranslation()
  const isWide = useMediaQuery(WIDE_QUERY)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)

  const tree = useAlbumTree()
  const album = albumId === undefined ? undefined : tree.data?.byId.get(albumId)
  const children = tree.data?.children.get(albumId ?? null) ?? []
  const path = album && tree.data ? pathTo(album, tree.data.byId) : []

  const mediaQuery = useAlbumMedia(albumId, { cursor, before })
  useLibraryUpdates()
  const media = mediaQuery.data?.items ?? []
  // A query without an album is disabled, and a disabled query stays "pending" forever.
  const mediaIsLoading = albumId !== undefined && mediaQuery.isPending
  const navigate = useNavigate()
  // The viewer follows the address: opening writes the medium into it, closing takes it out.
  // Only the first step is worth a history entry, so the back button closes the picture.
  const onCurrentChange = useCallback(
    (mediaId: string | undefined) => {
      if (albumId === undefined) return
      void navigate({
        to: '/albums/$albumId',
        params: { albumId },
        search: (previous: AlbumSearch) => {
          const next: AlbumSearch = { ...previous }
          delete next.medium
          if (mediaId !== undefined) next.medium = mediaId
          return next
        },
        replace: mediaId === undefined || medium !== undefined,
      })
    },
    [albumId, medium, navigate],
  )
  const viewer = useMediaViewer(media, { current: medium, onCurrentChange, social: true })
  useSocialUpdates()

  const title = album?.title ?? t('nav.albums')
  const columns = isDesktop ? 6 : isWide ? 5 : 3

  return (
    <AppShell title={title} active="albums">
      <div className="space-y-5 px-5 md:px-0">
        <LibraryHeader album={album} path={path} albums={children.length} tree={tree.data} />
        {album && <AlbumSocial key={album.id} albumId={album.id} />}

        {tree.isPending && <p className="text-base text-muted-foreground">{t('albums.loading')}</p>}
        {tree.isError && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}

        {tree.data &&
          children.length === 0 &&
          media.length === 0 &&
          !mediaIsLoading &&
          (album === undefined ? <EmptyLibrary /> : <EmptyAlbum />)}

        {children.length > 0 && (
          <section aria-label={t(album ? 'albums.subalbums' : 'albums.albums')}>
            <SectionHeading title={t(album ? 'albums.subalbums' : 'albums.albums')} />
            {/* Covers stay around the 150 to 190 px of the design: on a wide screen that
                means more columns, not larger tiles. */}
            <div className="mt-3 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7">
              {children.map((child) => (
                <AlbumCard key={child.id} album={child} />
              ))}
            </div>
          </section>
        )}

        {media.length > 0 && albumId !== undefined && (
          <section aria-label={t('albums.media')}>
            {/* The count is in the album's header already; saying it twice helps nobody. */}
            <SectionHeading title={t('albums.media')} />
            <div className="mt-3">
              <MediaGrid
                media={media}
                columns={columns}
                onOpen={(index) => {
                  viewer.open(index)
                }}
              />
            </div>
            <MediaPager
              albumId={albumId}
              shown={media.length}
              total={album?.media_count ?? media.length}
              prevCursor={mediaQuery.data?.prev_cursor ?? null}
              nextCursor={mediaQuery.data?.next_cursor ?? null}
              busy={mediaQuery.isFetching}
            />
          </section>
        )}
      </div>

      {viewer.panel}
    </AppShell>
  )
}

interface MediaPagerProps {
  albumId: string
  shown: number
  total: number
  prevCursor: string | null
  nextCursor: string | null
  busy: boolean
}

/**
 * Back and forth through the album, one page at a time.
 *
 * Both steps are links, not buttons: the page is part of the address, so it can be opened in a
 * second tab, kept as a bookmark and sent to somebody. There are no page numbers - a cursor
 * knows the medium it sits on, not how many lie in front of it.
 */
function MediaPager({ albumId, shown, total, prevCursor, nextCursor, busy }: MediaPagerProps) {
  const { t } = useTranslation()
  const scrollContainer = useScrollContainer()

  if (prevCursor === null && nextCursor === null) return null

  // A new page starts at its top; carrying the old scroll position over lands in the middle.
  const toTop = () => {
    scrollContainer?.scrollTo({ top: 0 })
  }

  return (
    <nav
      aria-label={t('albums.pager.label')}
      aria-busy={busy}
      className="mt-4 flex items-center justify-between gap-3"
    >
      <span className="min-w-0">
        {prevCursor !== null && (
          <Button asChild variant="outline">
            <Link
              to="/albums/$albumId"
              params={{ albumId }}
              search={{ before: prevCursor }}
              onClick={toTop}
            >
              <Symbol name="chevron_left" size={20} />
              {t('albums.pager.previous')}
            </Link>
          </Button>
        )}
      </span>

      <p role="status" className="text-xs-plus text-muted-foreground">
        {t('albums.pager.position', { shown, total })}
      </p>

      <span className="min-w-0">
        {nextCursor !== null && (
          <Button asChild variant="outline">
            <Link
              to="/albums/$albumId"
              params={{ albumId }}
              search={{ cursor: nextCursor }}
              onClick={toTop}
            >
              {t('albums.pager.next')}
              <Symbol name="chevron_right" size={20} />
            </Link>
          </Button>
        )}
      </span>
    </nav>
  )
}

interface LibraryHeaderProps {
  /** The album one is looking at, or undefined at the root of the tree. */
  album: Album | undefined
  path: Album[]
  albums: number
  tree: { items: Album[] } | undefined
}

/**
 * The same header on every level of the tree: where one is, what is here, what can be done.
 *
 * Its geometry does not depend on what it holds. The path is one line, the title one line, the
 * facts below it one line, and the actions sit in a lane of their own that keeps its height
 * whether there is a button in it or not. Otherwise walking into an album - where a sync button
 * appears - would push the tiles down, and the eye would have to find them again after every
 * click.
 */
function LibraryHeader({ album, path, albums, tree }: LibraryHeaderProps) {
  const { t } = useTranslation()

  const title = album?.title ?? t('albums.root')
  const media = album ? album.media_count : (tree?.items ?? []).reduce(count, 0)

  return (
    <header>
      <Path album={album} path={path} />

      <div className="mt-1 flex min-h-11 items-center justify-between gap-4">
        <div className="min-w-0">
          <Title text={title} />
          {/* One line, always: the facts of this level, as many as fit. */}
          <p className="mt-0.5 truncate text-xs-plus text-muted-foreground">
            {album === undefined
              ? t('albums.albumCount', { count: albums })
              : t('albums.count', { count: media })}
            {albums > 0 && album !== undefined && (
              <> · {t('albums.subalbumCount', { count: albums })}</>
            )}
            {album?.description && <> · {album.description}</>}
            {album?.last_sync_status === 'unavailable' && (
              <span className="text-destructive"> · {t('albums.unreachable')}</span>
            )}
          </p>
        </div>

        {/* The lane for actions keeps its height empty, so nothing below it moves. */}
        <div className="flex h-11 shrink-0 items-center gap-2">
          {album && <AlbumPlace key={album.id} albumId={album.id} />}
          {album?.is_source && <SyncAction album={album} />}
        </div>
      </div>
    </header>
  )
}

/** One step of the path. The same box whether it is a link or the place one is standing. */
const CRUMB = 'shrink-0 rounded px-1 py-0.5 text-muted-foreground'

/** How many steps below the root a narrow screen still spells out. */
const NARROW_STEPS = 2

/**
 * Where one is standing, from the root of the tree down to this album.
 *
 * A phone has room for four steps. Deeper than that, everything between the root and the last two
 * folds into a single "…", so the path stays on its line instead of pushing its end off the
 * screen. The "…" is no dead end: it leads to the album directly above the two that are spelled
 * out, and from there the whole path is visible again.
 */
function Path({ album, path }: { album: Album | undefined; path: Album[] }) {
  const { t } = useTranslation()
  const isWide = useMediaQuery(WIDE_QUERY)

  const folded = !isWide && path.length > NARROW_STEPS ? path.slice(0, -NARROW_STEPS) : []
  const steps = folded.length === 0 ? path : path.slice(-NARROW_STEPS)
  const above = folded.at(-1)

  return (
    // Every step carries the same padding, whether it leads anywhere or not, and the row is
    // pulled back by exactly that padding: the path then starts on the same line as the title
    // below it, on the tree and inside an album alike.
    <nav
      aria-label={t('albums.path')}
      className="-ml-1 flex h-7 flex-nowrap items-center gap-1 overflow-x-auto text-sm-plus"
    >
      {album === undefined ? (
        <span className={CRUMB}>{t('albums.root')}</span>
      ) : (
        <Link to="/albums" className={cn(CRUMB, 'hover:text-foreground')}>
          {t('albums.root')}
        </Link>
      )}
      {above && (
        <span className="flex shrink-0 items-center gap-1">
          <Chevron />
          <Link
            to="/albums/$albumId"
            params={{ albumId: above.id }}
            aria-label={t('albums.pathFolded', { title: above.title })}
            className={cn(CRUMB, 'hover:text-foreground')}
          >
            …
          </Link>
        </span>
      )}
      {steps.map((step, index) => (
        <span key={step.id} className="flex shrink-0 items-center gap-1">
          <Chevron />
          {index === steps.length - 1 ? (
            <span className={CRUMB}>{step.title}</span>
          ) : (
            <Link
              to="/albums/$albumId"
              params={{ albumId: step.id }}
              className={cn(CRUMB, 'hover:text-foreground')}
            >
              {step.title}
            </Link>
          )}
        </span>
      ))}
    </nav>
  )
}

/** What sits between two steps of the path. */
function Chevron() {
  return <Symbol name="chevron_right" size={15} className="text-muted-foreground/60" />
}

/**
 * The name of this level, big enough to be the page it is.
 *
 * From 768 px the shell already carries it as the page's only first-level heading, so the
 * visible one is decoration there; below that it is the heading itself.
 */
function Title({ text }: { text: string }) {
  const isWide = useMediaQuery(WIDE_QUERY)
  const className = 'truncate text-title font-semibold text-foreground'

  if (isWide) {
    return (
      <p aria-hidden="true" className={className}>
        {text}
      </p>
    )
  }
  return <h1 className={className}>{text}</h1>
}

/** "Sync now", and what the last one found - in the line above, where there is room for it. */
function SyncAction({ album }: { album: Album }) {
  const { t } = useTranslation()
  const sync = useAlbumSync(album.id)

  return (
    <>
      {sync.result && (
        <p
          role="status"
          className="hidden max-w-[240px] truncate text-xs-plus text-muted-foreground sm:block"
        >
          {syncSummary(sync.result, t)}
        </p>
      )}
      <Button
        variant="outline"
        disabled={sync.isRunning}
        onClick={() => {
          sync.start(true)
        }}
      >
        <Symbol name="sync" size={20} />
        {sync.isRunning ? t('albums.syncing') : t('albums.sync')}
      </Button>
    </>
  )
}

/**
 * What a sync changed, in words - only what actually happened, and one phrase for nothing.
 * A file seen for the first time is not "new" yet: it waits for a second listing that shows the
 * copy is finished. It still belongs here, or a file that is plainly there reads as no change.
 */
const SYNC_PARTS = ['added', 'waiting', 'restored', 'changed', 'moved', 'missing'] as const

function syncSummary(result: Record<string, unknown>, t: TFunction): string {
  const parts = SYNC_PARTS.map((part) => ({ part, count: Number(result[part] ?? 0) }))
    .filter(({ count }) => count > 0)
    .map(({ part, count }) => t(`albums.syncFound.${part}`, { count }))
  return parts.length > 0 ? parts.join(', ') : t('albums.syncNothing')
}

function count(total: number, album: Album): number {
  return total + album.media_count
}

/**
 * What sits on an album's tile.
 *
 * An album with pictures of its own shows the newest one. A folder that only holds folders would
 * be an empty box otherwise, so it shows up to four pictures from the albums below it: one fills
 * the tile, two share it, three put the first beside two smaller ones, four make a square.
 */
function AlbumCover({ album }: { album: Album }) {
  const covers = album.cover_urls.slice(0, 4)

  if (covers.length === 0) {
    return (
      <span className="flex h-full w-full items-center justify-center text-muted-foreground">
        <Symbol name="folder" size={28} filled={album.is_source} />
      </span>
    )
  }

  return (
    <span
      className={cn(
        'grid h-full w-full gap-px',
        covers.length > 1 && 'grid-cols-2',
        covers.length > 2 && 'grid-rows-2',
      )}
    >
      {covers.map((url, index) => (
        <img
          key={url}
          src={url}
          alt=""
          loading="lazy"
          decoding="async"
          className={cn(
            'h-full w-full object-cover',
            // Three pictures: the first one takes the whole left half.
            covers.length === 3 && index === 0 && 'row-span-2',
          )}
        />
      ))}
    </span>
  )
}

export function AlbumCard({ album }: { album: Album }) {
  const { t } = useTranslation()

  return (
    <Link
      to="/albums/$albumId"
      params={{ albumId: album.id }}
      aria-label={t('albums.open', { title: album.title })}
      className="group block text-left"
    >
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-secondary/60 transition group-hover:ring-1 group-hover:ring-primary/35">
        <AlbumCover album={album} />
        {album.media_count > 0 && (
          <Badge variant="count" className="absolute bottom-1.5 right-1.5">
            {album.media_count}
          </Badge>
        )}
      </div>
      <p className="mt-2 truncate text-base font-semibold text-foreground">{album.title}</p>
      <p className="truncate text-xs-plus text-muted-foreground">
        {album.child_count > 0
          ? t('albums.subalbumCount', { count: album.child_count })
          : t('albums.count', { count: album.media_count })}
      </p>
    </Link>
  )
}
