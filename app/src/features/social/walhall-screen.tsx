import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { EmptyNote } from '@/components/muninn/empty-note'
import { SectionHeading } from '@/components/muninn/section-heading'
import { AlbumCard } from '@/features/albums/albums-screen'
import { MediaGrid } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { useFavoriteAlbums, useFavoriteMedia, useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

/**
 * Walhall: what one keeps. The albums first, few and large, then every picture and video with
 * a star, the most recently kept first. Nobody else sees it.
 */
export function WalhallScreen({ medium }: { medium?: string | undefined }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const isWide = useMediaQuery(WIDE_QUERY)
  const albums = useFavoriteAlbums()
  const kept = useFavoriteMedia()
  useSocialUpdates()

  const media = useMemo(() => kept.data?.pages.flatMap((page) => page.items) ?? [], [kept.data])
  const onCurrentChange = useCallback(
    (mediaId: string | undefined) => {
      void navigate({
        to: '/favorites',
        search: mediaId === undefined ? {} : { medium: mediaId },
        replace: mediaId === undefined || medium !== undefined,
      })
    },
    [medium, navigate],
  )
  const viewer = useMediaViewer(media, { current: medium, onCurrentChange, social: true })

  const nothing =
    albums.isSuccess && kept.isSuccess && albums.data.length === 0 && media.length === 0

  return (
    <AppShell title={t('walhall.title')} active="profile">
      <div className="space-y-6 px-5 md:px-0">
        <p className="text-base text-muted-foreground">{t('walhall.description')}</p>

        {nothing && <EmptyNote>{t('walhall.empty')}</EmptyNote>}

        {albums.data && albums.data.length > 0 && (
          <section aria-label={t('walhall.albums')}>
            <SectionHeading title={t('walhall.albums')} />
            <div className="mt-3 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {albums.data.map((album) => (
                <AlbumCard key={album.id} album={album} />
              ))}
            </div>
          </section>
        )}

        {media.length > 0 && (
          <section aria-label={t('walhall.media')}>
            <SectionHeading title={t('walhall.media')} />
            <div className="mt-3">
              <MediaGrid
                media={media}
                columns={isDesktop ? 6 : isWide ? 5 : 3}
                onOpen={(index) => {
                  viewer.open(index)
                }}
                onEndReached={() => {
                  if (kept.hasNextPage && !kept.isFetchingNextPage) void kept.fetchNextPage()
                }}
              />
            </div>
          </section>
        )}
      </div>
      {viewer.panel}
    </AppShell>
  )
}
