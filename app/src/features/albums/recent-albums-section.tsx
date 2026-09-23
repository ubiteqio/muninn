import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { EmptyNote } from '@/components/muninn/empty-note'
import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { type Album, pathTo, useAlbumTree } from '@/features/albums/use-albums'
import { cn } from '@/lib/utils'

/** How many of the newest albums the start screen shows. */
const SHOWN = 6

function AlbumCard({ album, path, className }: { album: Album; path: string; className?: string }) {
  const { t } = useTranslation()

  return (
    <Link
      to="/albums/$albumId"
      params={{ albumId: album.id }}
      aria-label={t('albums.open', { title: album.title })}
      className={cn('group block text-left', className)}
    >
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-secondary/60 transition group-hover:ring-1 group-hover:ring-primary/35">
        {album.cover_urls[0] ? (
          <img
            src={album.cover_urls[0]}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-muted-foreground">
            <Symbol name="folder" size={22} />
          </span>
        )}
        <Badge variant="count" className="absolute bottom-1.5 right-1.5">
          {album.media_count}
        </Badge>
      </div>
      <p className="mt-2 truncate text-base font-semibold text-foreground">{album.title}</p>
      <p className="truncate text-xs-plus text-muted-foreground">{path}</p>
    </Link>
  )
}

/**
 * The albums Muninn saw most recently, newest first.
 *
 * "Recently added" means the folder, not the pictures in it: an album appears here when the
 * scanner first found it, which is the moment it became something one can open.
 *
 * Mobile: a horizontal scroller of 132 px covers. Desktop: two columns in the aside.
 * The section links to the whole album tree.
 */
export function RecentAlbumsSection({ layout = 'scroller' }: { layout?: 'scroller' | 'grid' }) {
  const { t } = useTranslation()
  const tree = useAlbumTree()

  const albums = (tree.data?.items ?? [])
    .filter((album) => album.is_source && album.media_count > 0)
    .sort((one, other) => other.created_at.localeCompare(one.created_at))
    .slice(0, SHOWN)

  const pathOf = (album: Album) =>
    tree.data
      ? pathTo(album, tree.data.byId)
          .slice(0, -1)
          .map((step) => step.title)
          .join(' › ')
      : ''

  return (
    <section aria-labelledby="albums-heading" aria-busy={tree.isPending}>
      <SectionHeading
        id="albums-heading"
        title={t('albums.title')}
        className={layout === 'scroller' ? 'px-5 lg:px-0' : undefined}
        action={
          <Link to="/albums" className="text-sm font-medium text-primary hover:text-accent">
            {t('albums.tree')}
          </Link>
        }
      />

      {tree.isPending ? (
        <AlbumsLoading layout={layout} />
      ) : albums.length === 0 ? (
        <EmptyNote className={cn(layout === 'scroller' && 'mx-5 lg:mx-0')}>
          {t('albums.emptyRecent')}
        </EmptyNote>
      ) : layout === 'scroller' ? (
        <div className="scroll-snap-x mt-3 flex scroll-px-5 gap-3 overflow-x-auto px-5">
          {albums.map((album) => (
            <AlbumCard
              key={album.id}
              album={album}
              path={pathOf(album)}
              className="w-[132px] shrink-0 snap-start"
            />
          ))}
        </div>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-3.5">
          {albums.map((album) => (
            <AlbumCard key={album.id} album={album} path={pathOf(album)} />
          ))}
        </div>
      )}
    </section>
  )
}

/**
 * The covers on their way: the same squares with the title and the path under them, in the row
 * the phone shows or the two columns of the aside.
 */
function AlbumsLoading({ layout }: { layout: 'scroller' | 'grid' }) {
  const cards = Array.from({ length: SHOWN }, (_, index) => (
    <div key={index} className={cn(layout === 'scroller' && 'w-[132px] shrink-0')}>
      <Placeholder className="aspect-square w-full rounded-lg" />
      {/* The title and the path under it take 42 px together, and so do these. */}
      <Placeholder className="mt-2 h-[19px] w-4/5" />
      <Placeholder className="h-[15px] w-3/5" />
    </div>
  ))

  return (
    <LoadingBody
      boxed={false}
      className={cn(
        'mt-3',
        layout === 'scroller' ? 'flex gap-3 overflow-hidden px-5' : 'grid grid-cols-2 gap-3.5',
      )}
    >
      {cards}
    </LoadingBody>
  )
}
