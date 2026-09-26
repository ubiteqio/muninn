import { Link, useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageHeading } from '@/components/layout/page-heading'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { MediaGrid } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { ChapterCard, ChapterCardLoading } from '@/features/smarts/chapter-card'
import {
  type Chapter,
  chaptersOf,
  type FaceStrip,
  pagesOf,
  type Shelf,
  useShelf,
  useSmarts,
} from '@/features/smarts/use-smarts'
import { cn } from '@/lib/utils'

/** The first cards are larger: a wall of equal tiles is a spreadsheet, not a place to browse. */
const LARGE = 2

/** How many cards stand there while the first answer is on its way. */
const LOADING_CARDS = 8

interface SmartsScreenProps {
  /** A shelf, when one is open: videos, documents, screenshots. */
  shelf?: string | undefined
  /** The medium shown full screen, from the address. */
  medium?: string | undefined
}

/**
 * Smarts: the library sorted by what is in it, for browsing rather than searching.
 *
 * Nothing here needs a machine. The chapters were found by a worker from the picture vectors
 * that are in the database anyway, and the shelves come out of what stage 5 wrote down. So this
 * screen is exactly as good while the AI machine is switched off - which is when somebody
 * usually sits down with it.
 */
export function SmartsScreen({ shelf, medium }: SmartsScreenProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const smarts = useSmarts()
  const chapters = useMemo(() => chaptersOf(smarts.data?.pages), [smarts.data])
  const first = smarts.data?.pages[0]

  const onCurrentChange = useCallback(
    (mediaId: string | undefined) => {
      void navigate({
        to: '/smarts',
        search: { ...(shelf ? { shelf } : {}), ...(mediaId ? { medium: mediaId } : {}) },
        replace: true,
      })
    },
    [navigate, shelf],
  )

  if (shelf !== undefined) {
    return <ShelfView shelf={shelf} medium={medium} onCurrentChange={onCurrentChange} />
  }

  return (
    <AppShell title={t('smarts.title')} active="albums">
      <div className="space-y-7">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PageHeading title={t('smarts.title')} description={t('smarts.description')} />
          <Dice chapters={chapters} />
        </div>

        {first && first.faces.length > 0 && <Faces faces={first.faces} />}
        {first && first.shelves.length > 0 && <Shelves shelves={first.shelves} />}

        <section aria-label={t('smarts.chapters')}>
          <SectionHeading
            title={t('smarts.chapters')}
            action={
              first ? (
                <span className="text-2xs text-muted-foreground">
                  {t('smarts.ofMedia', { count: first.media })}
                </span>
              ) : undefined
            }
          />

          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {smarts.isPending &&
              Array.from({ length: LOADING_CARDS }, (_, index) => (
                <ChapterCardLoading key={index} large={index < LARGE} />
              ))}
            {chapters.map((chapter, index) => (
              <ChapterCard key={chapter.id} chapter={chapter} large={index < LARGE} />
            ))}
          </div>

          {!smarts.isPending && chapters.length === 0 && <NoChapters />}

          {smarts.hasNextPage && (
            <div className="mt-5 flex justify-center">
              <Button
                variant="outline"
                disabled={smarts.isFetchingNextPage}
                onClick={() => {
                  void smarts.fetchNextPage()
                }}
              >
                {smarts.isFetchingNextPage ? t('smarts.loading') : t('smarts.more')}
              </Button>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  )
}

/**
 * What the Smarts look like before a night has passed over them: the chapters are built by the
 * worker, not by opening this page, so saying when they will be there is the whole message.
 */
function NoChapters() {
  const { t } = useTranslation()

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center px-6 text-center">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary/50">
        <Symbol name="auto_awesome" size={28} className="text-muted-foreground" />
      </span>
      <h2 className="mt-5 text-lg font-semibold text-foreground">{t('smarts.empty')}</h2>
      <p className="mt-2 max-w-[400px] text-base leading-relaxed text-muted-foreground">
        {t('smarts.emptyNote')}
      </p>
    </div>
  )
}

/**
 * "Würfeln": one chapter at random, played as a slideshow.
 *
 * The point of a heap of 8000 pictures is that nobody knows what is in it any more. A button
 * that picks for you is the shortest way back in - and it costs nothing, because the chapters
 * are already there.
 */
function Dice({ chapters }: { chapters: Chapter[] }) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <Button
      disabled={chapters.length === 0}
      title={t('smarts.diceHint')}
      onClick={() => {
        const chosen = chapters[Math.floor(Math.random() * chapters.length)]
        if (chosen) {
          void navigate({
            to: '/smarts/$chapterId',
            params: { chapterId: chosen.id },
            search: { play: true },
          })
        }
      }}
    >
      <Symbol name="casino" size={18} />
      {t('smarts.dice')}
    </Button>
  )
}

/** Who turns up most: round faces, and each one leads to that person's page. */
function Faces({ faces }: { faces: FaceStrip[] }) {
  const { t } = useTranslation()

  return (
    <section aria-label={t('smarts.faces')}>
      <SectionHeading title={t('smarts.faces')} />
      <ul className="no-scrollbar mt-3 flex gap-3 overflow-x-auto pb-1">
        {faces.map((face) => (
          <li key={face.person_id} className="shrink-0">
            <Link
              to="/people/$personId"
              params={{ personId: face.person_id }}
              className="group flex w-[72px] flex-col items-center gap-1.5"
            >
              <span className="h-[72px] w-[72px] overflow-hidden rounded-full bg-secondary/60 ring-1 ring-hairline/10 transition group-hover:ring-2 group-hover:ring-primary/50">
                {face.face?.crop && (
                  <img
                    src={face.face.crop}
                    alt=""
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                )}
              </span>
              <span className="w-full truncate text-center text-2xs font-medium text-foreground">
                {face.name}
              </span>
              <span className="text-3xs tabular-nums text-muted-foreground">{face.count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The shelves: everything with one trait, counted. An empty shelf is never offered. */
function Shelves({ shelves }: { shelves: Shelf[] }) {
  const { t } = useTranslation()

  return (
    <section aria-label={t('smarts.shelves')}>
      <SectionHeading title={t('smarts.shelves')} />
      <ul className="mt-3 flex flex-wrap gap-2">
        {shelves.map((shelf) => (
          <li key={shelf.key}>
            <Link
              to="/smarts"
              search={{ shelf: shelf.key }}
              className={cn(
                'flex items-center gap-2 rounded-full border border-hairline/10 bg-card px-3 py-1.5 text-sm',
                'transition hover:border-primary/40 hover:bg-secondary/60',
              )}
            >
              <Symbol name={SHELF_ICON[shelf.key] ?? 'label'} size={16} />
              <span className="font-medium">{t(`smarts.shelf.${shelf.key}`)}</span>
              <span className="tabular-nums text-muted-foreground">{shelf.count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

const SHELF_ICON: Record<string, string> = {
  people: 'group',
  crowd: 'groups',
  video: 'movie',
  document: 'description',
  screenshot: 'smartphone',
  text: 'text_fields',
}

/** One shelf, as a grid. The same viewer as everywhere else opens from it. */
function ShelfView({
  shelf,
  medium,
  onCurrentChange,
}: {
  shelf: string
  medium: string | undefined
  onCurrentChange: (mediaId: string | undefined) => void
}) {
  const { t } = useTranslation()
  const query = useShelf(shelf)
  const media = useMemo(() => pagesOf(query.data?.pages), [query.data])
  const viewer = useMediaViewer(media, { current: medium, onCurrentChange, social: true })

  return (
    <AppShell title={t(`smarts.shelf.${shelf}`)} active="albums">
      <div className="space-y-5">
        <Link
          to="/smarts"
          className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-accent"
        >
          <Symbol name="arrow_back" size={16} />
          {t('smarts.back')}
        </Link>
        <PageHeading
          title={t(`smarts.shelf.${shelf}`)}
          description={t('smarts.shelfCount', { count: media.length })}
        />

        <MediaGrid
          media={media}
          columns={4}
          onOpen={(index) => {
            viewer.open(index)
          }}
          onEndReached={() => {
            if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage()
          }}
        />
      </div>
      {viewer.panel}
    </AppShell>
  )
}
