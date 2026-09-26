import { Link, useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageHeading } from '@/components/layout/page-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { MediaGrid, MediaGridLoading } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { useSearchAbilities } from '@/features/search/use-search'
import { pagesOf, spanOf, titleOf, useChapter } from '@/features/smarts/use-smarts'
import { useSmartsUpdates } from '@/features/smarts/use-smarts-updates'
import { useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

/** How long one picture stands in the slideshow. Long enough to look, short enough to go on. */
const SLIDESHOW_MS = 3500

interface ChapterScreenProps {
  chapterId: string
  /** Start the slideshow at once - what "Würfeln" and the play button on a card ask for. */
  play?: boolean | undefined
  medium?: string | undefined
}

/**
 * One chapter: everything that looks alike, the clearest examples first.
 *
 * It can be scrolled like any album, or watched: the same viewer everywhere else uses, with a
 * slideshow that moves on by itself. Ordered by how close each picture is to the one the group
 * was built around, so the first screen is the chapter at its most obvious.
 */
export function ChapterScreen({ chapterId, play, medium }: ChapterScreenProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  // The same tiles as everywhere else: more columns on a wide screen, not larger pictures.
  const isWide = useMediaQuery(WIDE_QUERY)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const columns = isDesktop ? 6 : isWide ? 5 : 3
  const abilitiesQuery = useSearchAbilities()
  const abilities = abilitiesQuery.data
  const query = useChapter(chapterId)
  useSmartsUpdates()
  const media = useMemo(() => pagesOf(query.data?.pages), [query.data])
  const chapter = query.data?.pages[0]?.chapter

  const onCurrentChange = useCallback(
    (mediaId: string | undefined) => {
      void navigate({
        to: '/smarts/$chapterId',
        params: { chapterId },
        search: mediaId ? { medium: mediaId } : {},
        replace: true,
      })
    },
    [chapterId, navigate],
  )

  const onSimilar = useCallback(
    (mediaId: string) => {
      void navigate({ to: '/search', search: { similar: mediaId } })
    },
    [navigate],
  )

  // Asked for by the address, so a slideshow can be sent to somebody: it starts on the first
  // picture unless the address names another one.
  const playing = play === true
  const viewer = useMediaViewer(media, {
    // The viewer builds its buttons when it opens, so it waits until "Ähnliche Bilder" is decided.
    current: abilitiesQuery.isPending
      ? undefined
      : playing && medium === undefined
        ? media[0]?.id
        : medium,
    onCurrentChange,
    // Nothing to compare without a picture model: the button would only lead to an empty page.
    onSimilar: abilities?.pictures ? onSimilar : undefined,
    social: true,
    ...(playing ? { slideshow: SLIDESHOW_MS } : {}),
  })
  useSocialUpdates()

  const title = chapter ? titleOf(chapter, t) : t('smarts.unnamed')

  return (
    <AppShell title={title} active="albums">
      <div className="space-y-5 px-5 md:px-0">
        <Link
          to="/smarts"
          className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-accent"
        >
          <Symbol name="arrow_back" size={16} />
          {t('smarts.back')}
        </Link>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <PageHeading
            title={title}
            {...(chapter
              ? {
                  description: [
                    t(`smarts.kind.${chapter.kind}`),
                    t('smarts.count', { count: chapter.size }),
                    chapter.albums > 1 ? t('smarts.fromAlbums', { count: chapter.albums }) : null,
                    spanOf(chapter),
                  ]
                    .filter(Boolean)
                    .join(' · '),
                }
              : {})}
          />
          <div className="flex gap-2">
            {/* Only where it comes from one folder; most chapters draw from many. */}
            {chapter?.album_id && (
              <Button variant="outline" asChild>
                <Link to="/albums/$albumId" params={{ albumId: chapter.album_id }}>
                  <Symbol name="folder" size={18} />
                  {t('smarts.toAlbum')}
                </Link>
              </Button>
            )}
            <Button
              disabled={media.length === 0}
              onClick={() => {
                viewer.open(0)
              }}
            >
              <Symbol name="play_arrow" size={18} filled />
              {t('smarts.play')}
            </Button>
          </div>
        </div>

        {/* The tags the name was made of: what these pictures have in common, in their own words. */}
        {chapter && chapter.tags.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {chapter.tags.map((tag) => (
              <li
                key={tag}
                className="rounded-badge bg-secondary/60 px-2 py-0.5 text-2xs font-medium text-muted-foreground"
              >
                {tag}
              </li>
            ))}
          </ul>
        )}

        {query.isPending && <MediaGridLoading columns={columns} tiles={chapter?.size} />}

        {media.length > 0 && (
          <MediaGrid
            media={media}
            columns={columns}
            onOpen={(index) => {
              viewer.open(index)
            }}
            onEndReached={() => {
              if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage()
            }}
          />
        )}
      </div>
      {viewer.panel}
    </AppShell>
  )
}
