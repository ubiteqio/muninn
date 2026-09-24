import { useIsFetching } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { Knotwork } from '@/components/muninn/knotwork'
import { LoadingBody } from '@/components/muninn/placeholder'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { useAlbumTree } from '@/features/albums/use-albums'
import { useLibraryUpdates } from '@/features/albums/use-library-updates'
import { formatDuration } from '@/features/media/format'
import { MediaGrid, MediaGridLoading } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { useOverview } from '@/features/overview/use-overview'
import { PeopleRow } from '@/features/people/people-row'
import {
  type MediaKind,
  type SearchSort,
  useSearch,
  useSearchAbilities,
} from '@/features/search/use-search'
import { useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import type { SearchParams } from '@/routes'

/**
 * Mímir: what was typed, and everything in the library that answers it.
 *
 * Everything that makes up a search stands in the address - the words, the chips, an open
 * medium - so a search can be sent to somebody, and the back button undoes the last step.
 */
export function SearchScreen({
  q = '',
  kind,
  sort,
  year,
  place,
  camera,
  album,
  similar,
  medium,
}: SearchParams) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const isWide = useMediaQuery(WIDE_QUERY)
  const search = useSearch({ q, kind, sort, year, place, camera, album, similar })
  const abilitiesQuery = useSearchAbilities()
  const abilities = abilitiesQuery.data
  // Only once it is known: a page that is still asking says nothing about missing models.
  const withoutPictures = abilities !== undefined && !abilities.pictures
  // Set up and answering. Asked again every half minute, so the field follows the machine.
  const aiReady = abilities?.ready === true
  // Any search on its way, wherever it was started - the field on this page or the one in the
  // header, which is the only one on a desktop.
  const looking = useIsFetching({ queryKey: ['media', 'search'] }) > 0
  useLibraryUpdates()

  const change = useCallback(
    (next: Changes, replace = false) => {
      void navigate({
        to: '/search',
        // Unset and empty values leave the address rather than stand in it as "undefined".
        search: (previous: SearchParams) =>
          Object.fromEntries(
            Object.entries({ ...previous, ...next }).filter(
              ([, value]) => value !== undefined && value !== '',
            ),
          ) as SearchParams,
        replace,
      })
    },
    [navigate],
  )

  const hits = useMemo(() => search.data?.pages.flatMap((page) => page.items) ?? [], [search.data])
  const media = useMemo(() => hits.map((hit) => hit.media), [hits])
  const moments = useMemo(
    () =>
      new Map(
        hits.flatMap((hit) =>
          hit.moment === null || hit.moment === undefined ? [] : [[hit.media.id, hit.moment]],
        ),
      ),
    [hits],
  )
  const notes = useMemo(
    () =>
      new Map(
        [...moments].map(([id, second]) => [
          id,
          t('search.at', { time: formatDuration(Math.floor(second)) || '0:00' }),
        ]),
      ),
    [moments, t],
  )

  const onCurrentChange = useCallback(
    (mediaId: string | undefined) => {
      change({ medium: mediaId }, mediaId === undefined || medium !== undefined)
    },
    [change, medium],
  )
  const onSimilar = useCallback(
    (mediaId: string) => {
      change({ similar: mediaId, medium: undefined, q: undefined, kind: undefined })
    },
    [change],
  )
  const viewer = useMediaViewer(media, {
    // The viewer builds its buttons when it opens, so it waits until "Ähnliche Bilder" is decided.
    current: abilitiesQuery.isPending ? undefined : medium,
    onCurrentChange,
    startAt: moments,
    // Nothing to compare without a picture model: the button would only lead to an empty page.
    onSimilar: abilities?.pictures ? onSimilar : undefined,
    social: true,
  })
  useSocialUpdates()

  const understood = search.data?.pages[0]?.understood
  const degraded = search.data?.pages.some((page) => page.degraded) ?? false
  const asked = q.trim().length > 0 || similar !== undefined
  const columns = isDesktop ? 6 : isWide ? 5 : 3

  return (
    <AppShell title={t('nav.search')} active="search">
      <div className="space-y-4 px-5 md:px-0">
        {/* On the phone there is no header with a search field; the page brings its own. */}
        <SearchField
          key={q}
          initial={q}
          className="md:hidden"
          ai={aiReady}
          busy={looking}
          onSearch={(words) => {
            change({ q: words, similar: undefined, medium: undefined })
          }}
        />

        {similar !== undefined ? (
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-md font-semibold text-foreground">{t('search.similarTitle')}</h2>
            <button
              type="button"
              className="text-xs-plus text-accent underline-offset-2 hover:underline"
              onClick={() => {
                change({ similar: undefined, medium: undefined })
              }}
            >
              {t('search.backToSearch')}
            </button>
          </div>
        ) : (
          asked && (
            <>
              <Filters
                year={year}
                place={place}
                camera={camera}
                album={album}
                onChange={(next) => {
                  change({ ...next, medium: undefined }, true)
                }}
              />
              <Chips
                kind={kind}
                sort={sort}
                period={understood ? period(understood.date_from, understood.date_until, t) : null}
                places={understood?.places ?? []}
                persons={understood?.persons ?? []}
                onKind={(value) => {
                  change({ kind: value, medium: undefined }, true)
                }}
                onSort={(value) => {
                  change(
                    { sort: value === 'relevance' ? undefined : value, medium: undefined },
                    true,
                  )
                }}
              />
            </>
          )
        )}

        {withoutPictures && q.trim().length > 0 && (
          <p className="flex items-start gap-2 rounded-md border border-hairline/10 bg-secondary/40 px-3 py-2 text-base text-muted-foreground">
            <Symbol name="info" size={18} className="mt-px shrink-0" />
            {t('search.withoutPictures')}
          </p>
        )}

        {degraded && (
          <p className="flex items-start gap-2 rounded-md border border-hairline/10 bg-secondary/40 px-3 py-2 text-base text-muted-foreground">
            <Symbol name="warning" size={18} className="mt-px shrink-0" />
            {t('search.degraded')}
          </p>
        )}

        {!asked && (
          <PeopleRow
            onPerson={(name) => {
              change({ q: name, similar: undefined, medium: undefined })
            }}
          />
        )}
        {!asked && <Hint mode={withoutPictures ? 'words' : aiReady ? 'ai' : 'resting'} />}
        {asked && search.isPending && <ResultsLoading columns={columns} />}
        {search.isError && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}
        {asked && search.isSuccess && media.length === 0 && (
          <p className="py-10 text-center text-md text-muted-foreground">{t('search.nothing')}</p>
        )}

        {media.length > 0 && (
          <section aria-label={t('search.results')}>
            <MediaGrid
              media={media}
              columns={columns}
              notes={notes}
              onOpen={(index) => {
                viewer.open(index)
              }}
              onEndReached={() => {
                if (search.hasNextPage && !search.isFetchingNextPage) void search.fetchNextPage()
              }}
            />
          </section>
        )}
      </div>
      {viewer.panel}
    </AppShell>
  )
}

/**
 * What stands there while the hits are on their way: the grid in its shape, rather than one
 * line of text under the chips. The pictures land in the rows that are already held, so the eye
 * stays where it was instead of following a page that unfolds under it.
 */
function ResultsLoading({ columns }: { columns: number }) {
  const { t } = useTranslation()

  return (
    <section aria-busy="true" aria-label={t('search.results')}>
      <LoadingBody boxed={false} label={t('search.searching')}>
        <MediaGridLoading columns={columns} />
      </LoadingBody>
    </section>
  )
}

/** A change to the address: a value to set, or undefined to take it out. */
type Changes = { [Key in keyof SearchParams]?: SearchParams[Key] | undefined }

/**
 * The field itself: the header's on the desktop, the page's own on the phone. It starts from
 * what the address says; whoever shows it gives it a key, so a new search starts it afresh.
 *
 * It shows what it can do. With the models answering it is the accent colour and asks to be
 * described to; without them it is the plain field it has always been, because then it really
 * is a search for words. Promising more than the machine can deliver would be worse than the
 * plain field.
 */
export function SearchField({
  initial,
  onSearch,
  className,
  ai = false,
  busy = false,
}: {
  initial: string
  onSearch: (words: string) => void
  className?: string
  /** The picture and word models are set up and their machine answers. */
  ai?: boolean
  /** A search is on its way; the button rests and the bar runs until it is back. */
  busy?: boolean
}) {
  const { t } = useTranslation()
  const [words, setWords] = useState(initial)
  const ready = words.trim().length > 0

  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault()
        if (ready) onSearch(words.trim())
      }}
      className={cn('relative min-w-0', className)}
    >
      <Symbol
        name={ai ? 'auto_awesome' : 'search'}
        size={20}
        className={cn(
          'pointer-events-none absolute left-3 top-1/2 -translate-y-1/2',
          ai ? 'text-accent' : 'text-muted-foreground',
        )}
      />
      <Input
        type="search"
        className={cn('pl-10 pr-14 sm:pr-28', ai && 'border-accent/40')}
        value={words}
        onChange={(event) => {
          setWords(event.target.value)
        }}
        placeholder={t(ai ? 'search.placeholderAi' : 'search.placeholder')}
        aria-label={t('search.label')}
      />
      <Button
        type="submit"
        size="sm"
        disabled={busy || !ready}
        aria-label={t('search.submit')}
        className="absolute right-1.5 top-1/2 h-8 -translate-y-1/2 gap-1.5 px-2.5 sm:px-3"
      >
        <Symbol name={busy ? 'sync' : 'search'} size={18} className={cn(busy && 'animate-spin')} />
        <span className="hidden sm:inline">{t('search.submit')}</span>
      </Button>
      {busy && (
        <span
          aria-hidden="true"
          className="absolute inset-x-3 -bottom-1 h-0.5 overflow-hidden rounded-full bg-accent/15"
        >
          <span className="block h-full w-1/4 animate-sweep rounded-full bg-accent" />
        </span>
      )}
    </form>
  )
}

interface Choice {
  value: string
  label: string
  /** How many media are behind it, where that is known. */
  note?: string
}

/**
 * One filter as a chip that opens its list: the year, the town, the camera, the album.
 *
 * What can be chosen comes from the library itself - the overview counts the years, towns and
 * cameras it really has, the tree knows the albums - so nothing is offered that finds nothing.
 * A filter with nothing to offer is not shown at all.
 */
function Picker({
  icon,
  label,
  chosen,
  choices,
  onChoose,
}: {
  icon: string
  label: string
  chosen: string | undefined
  choices: Choice[]
  onChoose: (value: string | undefined) => void
}) {
  const { t } = useTranslation()
  if (choices.length === 0) return null
  const shown = choices.find((choice) => choice.value === chosen)?.label

  return (
    <span className="flex items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs-plus transition',
              shown === undefined
                ? 'bg-secondary text-muted-foreground hover:text-foreground'
                : 'bg-accent/15 text-foreground',
              shown === undefined ? 'rounded-full' : 'rounded-l-full rounded-r-none pr-1.5',
            )}
          >
            <Symbol name={icon} size={14} />
            {shown ?? label}
            <Symbol name="expand_more" size={14} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="max-h-72 overflow-y-auto">
          {choices.map((choice) => (
            <DropdownMenuItem
              key={choice.value}
              onSelect={() => {
                onChoose(choice.value)
              }}
            >
              <span className="flex-1">{choice.label}</span>
              {choice.note !== undefined && (
                <span className="ml-3 tabular-nums text-muted-foreground">{choice.note}</span>
              )}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {shown !== undefined && (
        <button
          type="button"
          aria-label={t('search.filter.clear', { label })}
          className="rounded-r-full bg-accent/15 py-1 pl-0.5 pr-2 text-foreground transition hover:bg-accent/25"
          onClick={() => {
            onChoose(undefined)
          }}
        >
          <Symbol name="close" size={14} />
        </button>
      )}
    </span>
  )
}

/**
 * The filters one chooses, beside the ones the words already carry.
 *
 * Everything offered comes from the library itself, with how much is behind it, so no choice
 * leads to an empty page. Each stands in the address, so a narrowed search can be sent to
 * somebody and the back button undoes one choice at a time.
 */
function Filters({
  year,
  place,
  camera,
  album,
  onChange,
}: {
  year: number | undefined
  place: string | undefined
  camera: string | undefined
  album: string | undefined
  onChange: (next: Changes) => void
}) {
  const { t } = useTranslation()
  const overview = useOverview()
  const tree = useAlbumTree()
  const many = (count: number) => count.toLocaleString('de-DE')

  const years: Choice[] = [...(overview.data?.years ?? [])]
    .sort((a, b) => b.year - a.year)
    .map((one) => ({
      value: String(one.year),
      label: String(one.year),
      note: many(one.photos + one.videos),
    }))
  const towns: Choice[] = (overview.data?.towns ?? []).map((one) => ({
    value: one.name,
    label: one.country ? `${one.name}, ${one.country}` : one.name,
    note: many(one.count),
  }))
  const cameras: Choice[] = (overview.data?.cameras ?? []).map((one) => ({
    value: one.name,
    label: one.name,
    note: many(one.count),
  }))
  const albums: Choice[] = [...(tree.data?.items ?? [])]
    .sort((a, b) => a.relative_path.localeCompare(b.relative_path, 'de'))
    .map((one) => ({ value: one.id, label: one.relative_path }))

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Picker
        icon="history"
        label={t('search.filter.year')}
        chosen={year === undefined ? undefined : String(year)}
        choices={years}
        onChoose={(value) => {
          onChange({ year: value === undefined ? undefined : Number(value) })
        }}
      />
      <Picker
        icon="map"
        label={t('search.filter.place')}
        chosen={place}
        choices={towns}
        onChoose={(value) => {
          onChange({ place: value })
        }}
      />
      <Picker
        icon="photo_camera"
        label={t('search.filter.camera')}
        chosen={camera}
        choices={cameras}
        onChoose={(value) => {
          onChange({ camera: value })
        }}
      />
      <Picker
        icon="folder"
        label={t('search.filter.album')}
        chosen={album}
        choices={albums}
        onChoose={(value) => {
          onChange({ album: value })
        }}
      />
    </div>
  )
}

function Chips({
  kind,
  sort,
  period: range,
  places,
  persons,
  onKind,
  onSort,
}: {
  kind: MediaKind | undefined
  sort: SearchSort | undefined
  period: string | null
  places: readonly string[]
  persons: readonly string[]
  onKind: (kind: MediaKind | undefined) => void
  onSort: (sort: SearchSort) => void
}) {
  const { t } = useTranslation()
  const kinds: { value: MediaKind | undefined; label: string }[] = [
    { value: undefined, label: t('search.kind.all') },
    { value: 'image', label: t('search.kind.image') },
    { value: 'video', label: t('search.kind.video') },
  ]
  const sorts: { value: SearchSort; label: string }[] = [
    { value: 'relevance', label: t('search.sort.relevance') },
    { value: 'date', label: t('search.sort.date') },
  ]

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label={t('search.kind.label')} className="flex gap-1.5">
        {kinds.map((option) => (
          <Chip
            key={option.label}
            pressed={kind === option.value}
            onClick={() => {
              onKind(option.value)
            }}
          >
            {option.label}
          </Chip>
        ))}
      </div>
      <span aria-hidden="true" className="mx-1 h-4 w-px bg-hairline/20" />
      <div role="group" aria-label={t('search.sort.label')} className="flex gap-1.5">
        {sorts.map((option) => (
          <Chip
            key={option.value}
            pressed={(sort ?? 'relevance') === option.value}
            onClick={() => {
              onSort(option.value)
            }}
          >
            {option.label}
          </Chip>
        ))}
      </div>
      {/* The period found in the words: taken as a filter, and shown, so nobody wonders why
          the results stop at one year. */}
      {range && (
        <span className="flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs-plus text-foreground">
          <Symbol name="history" size={14} />
          {range}
        </span>
      )}
      {/* And for people: "Oma Lena" only shows photos with both of them. */}
      {persons.map((person) => (
        <span
          key={person}
          className="flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs-plus text-foreground"
        >
          <Symbol name="person" size={14} />
          {person}
        </span>
      ))}
      {/* The same for places: "Toskana" only shows photos from there. */}
      {places.map((place) => (
        <span
          key={place}
          className="flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs-plus text-foreground"
        >
          <Symbol name="map" size={14} />
          {place}
        </span>
      ))}
    </div>
  )
}

function Chip({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        'rounded-full border px-3 py-1 text-xs-plus transition',
        pressed
          ? 'border-accent bg-accent/15 text-foreground'
          : 'border-hairline/15 text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

/** Before anything is typed: what can be asked, rather than an empty page. */
/**
 * What to type, in the words of the search one actually has.
 *
 * "words" when no models are set up, "resting" when they are but their machine is away - saying
 * "describe what you are looking for" to somebody who will only get a word search is worse than
 * saying nothing.
 */
function Hint({ mode }: { mode: 'words' | 'resting' | 'ai' }) {
  const { t } = useTranslation()
  const said = {
    words: 'search.hintWithoutPictures',
    resting: 'search.hintResting',
    ai: 'search.hint',
  }[mode]
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center">
      <Knotwork className="w-24" />
      <p className="max-w-[360px] text-md text-muted-foreground">{t(said)}</p>
    </div>
  )
}

/** "2012", "Juni – August 2012", "2010 – 2014": the period in words. */
export function period(
  from: string | null | undefined,
  until: string | null | undefined,
  t: ReturnType<typeof useTranslation>['t'],
): string | null {
  if (!from || !until) return null
  const start = new Date(`${from}T00:00:00Z`)
  const end = new Date(new Date(`${until}T00:00:00Z`).getTime() - 86_400_000)
  const month = (date: Date) => date.toLocaleDateString('de-DE', { month: 'long', timeZone: 'UTC' })
  const year = (date: Date) => String(date.getUTCFullYear())

  const wholeYears = start.getUTCMonth() === 0 && end.getUTCMonth() === 11
  if (wholeYears) {
    return year(start) === year(end) ? year(start) : `${year(start)} – ${year(end)}`
  }
  if (start.getUTCMonth() === end.getUTCMonth() && year(start) === year(end)) {
    return `${month(start)} ${year(start)}`
  }
  const from_ = year(start) === year(end) ? month(start) : `${month(start)} ${year(start)}`
  return t('search.period', { from: from_, until: `${month(end)} ${year(end)}` })
}
