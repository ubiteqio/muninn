import { Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { MediaGrid } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { Face } from '@/features/people/face'
import { FaceCheckDialog } from '@/features/people/face-check-dialog'
import { NameDialog } from '@/features/people/name-dialog'
import {
  type FaceFilter,
  type FaceView,
  useAnswer,
  useConfirmMany,
  useMerge,
  usePeople,
  usePerson,
  usePersonFaces,
  usePersonMedia,
  useUpdatePerson,
} from '@/features/people/use-people'
import { useSearchAbilities } from '@/features/search/use-search'
import { useSocialUpdates } from '@/features/social/use-social'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'

type Tab = 'photos' | 'faces'

/**
 * One person: every photo they are in, and their faces one by one - where a wrong one is taken
 * out with a tap. Renaming, merging with another person and hiding a stranger live here too.
 */
export function PersonScreen({ personId }: { personId: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const isWide = useMediaQuery(WIDE_QUERY)
  const person = usePerson(personId)
  const media = usePersonMedia(personId)
  const [tab, setTab] = useState<Tab>('photos')
  const [current, setCurrent] = useState<string | undefined>()
  const [renaming, setRenaming] = useState(false)
  const [merging, setMerging] = useState(false)
  const update = useUpdatePerson(personId)
  const abilities = useSearchAbilities()
  const pictures = abilities.data?.pictures ?? false
  const viewer = useMediaViewer(media.media, {
    // The viewer builds its buttons when it opens, so it waits until "Ähnliche Bilder" is decided.
    current: abilities.isPending ? undefined : current,
    onCurrentChange: setCurrent,
    social: true,
    // Nothing to compare without a picture model.
    onSimilar: pictures
      ? (mediaId: string) => {
          void navigate({ to: '/search', search: { similar: mediaId } })
        }
      : undefined,
  })
  useSocialUpdates()

  const data = person.data
  const columns = isDesktop ? 6 : isWide ? 5 : 3

  return (
    <AppShell title={data?.name ?? t('people.title')} active="people">
      <div className="space-y-6 px-5 md:px-0">
        <Link
          to="/people"
          className="inline-flex items-center gap-1 text-sm-plus text-muted-foreground hover:text-foreground"
        >
          <Symbol name="arrow_back" size={18} />
          {t('people.title')}
        </Link>

        {person.isError && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}
        {data && (
          <header className="flex flex-wrap items-center gap-5">
            <Face src={data.cover?.crop} size={96} />
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-title font-semibold text-foreground">{data.name}</h1>
              <p className="mt-1 text-base text-muted-foreground">
                {t('people.photos', { count: data.media })}
                {data.hidden && <> · {t('people.isHidden')}</>}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setRenaming(true)
                }}
              >
                {t('people.rename')}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setMerging(true)
                }}
              >
                {t('people.merge')}
              </Button>
              {data.hidden ? (
                <Button
                  variant="outline"
                  disabled={update.isPending}
                  onClick={() => {
                    update.mutate({ hidden: false })
                  }}
                >
                  {t('people.show')}
                </Button>
              ) : (
                <ConfirmDialog
                  trigger={<Button variant="outline">{t('people.hide')}</Button>}
                  title={t('people.hideTitle', { name: data.name })}
                  description={t('people.hideText')}
                  confirmLabel={t('people.hide')}
                  cancelLabel={t('common.cancel')}
                  closeLabel={t('common.close')}
                  pending={update.isPending}
                  onConfirm={async () => {
                    await update.mutateAsync({ hidden: true })
                  }}
                />
              )}
            </div>
          </header>
        )}

        <div role="tablist" className="flex gap-2">
          {(['photos', 'faces'] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              className={cn(
                'rounded-full border px-3 py-1 text-sm-plus transition',
                tab === value
                  ? 'border-accent bg-accent/15 text-foreground'
                  : 'border-hairline/10 text-muted-foreground hover:text-foreground',
              )}
              onClick={() => {
                setTab(value)
              }}
            >
              {t(value === 'photos' ? 'people.tabPhotos' : 'people.tabFaces')}
            </button>
          ))}
        </div>

        {tab === 'photos' ? (
          <MediaGrid
            media={media.media}
            columns={columns}
            onOpen={(index) => {
              setCurrent(media.media[index]?.id)
            }}
            onEndReached={() => {
              if (media.hasNextPage && !media.isFetchingNextPage) void media.fetchNextPage()
            }}
          />
        ) : (
          data && (
            <FacesTab
              personId={personId}
              name={data.name}
              counts={{
                all: data.faces,
                auto: data.faces_auto,
                twice: data.faces_twice,
              }}
            />
          )
        )}
      </div>

      {data && renaming && (
        <NameDialog
          open={renaming}
          onOpenChange={setRenaming}
          title={t('people.rename')}
          faces={[]}
          persons={[]}
          initial={data.name}
          pending={update.isPending}
          failed={update.isError}
          onName={(name) => {
            update.mutate(
              { name },
              {
                onSuccess: () => {
                  setRenaming(false)
                },
              },
            )
          }}
        />
      )}
      {data && merging && (
        <MergeDialog
          personId={personId}
          name={data.name}
          open={merging}
          onOpenChange={setMerging}
          onMerged={(into) => {
            void navigate({ to: '/people/$personId', params: { personId: into } })
          }}
        />
      )}
      {viewer.panel}
    </AppShell>
  )
}

const FILTERS: (FaceFilter | undefined)[] = [undefined, 'auto', 'twice']

/**
 * Their faces one by one: a wrong one leaves the person with a tap. To check them, the faces
 * Muninn gave on its own, or those where the person is twice in one photo, can be shown alone;
 * a tap on a face shows the whole photo with it marked.
 */
function FacesTab({
  personId,
  name,
  counts,
}: {
  personId: string
  name: string
  /** How many faces each filter holds, so a chip can say so before anybody scrolls. */
  counts: { all: number; auto: number; twice: number }
}) {
  const { t } = useTranslation()
  const [only, setOnly] = useState<FaceFilter | undefined>(undefined)
  const [checking, setChecking] = useState<FaceView | null>(null)
  const faces = usePersonFaces(personId, only)
  const answer = useAnswer()
  const confirmMany = useConfirmMany()
  const all = faces.data?.pages.flatMap((page) => page.items) ?? []
  // Only what is on the screen. A button that reached the whole list would stand by faces
  // nobody had looked at, and a wrong one vouches just as loudly as a right one.
  const muninns = all.filter((face) => face.assigned_by === 'auto')

  return (
    <div>
      <p className="text-base text-muted-foreground">{t('people.facesHint', { name })}</p>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={t('people.filter')}>
        {FILTERS.map((filter) => (
          <Button
            key={filter ?? 'all'}
            size="sm"
            variant={only === filter ? 'default' : 'outline'}
            aria-pressed={only === filter}
            onClick={() => {
              setOnly(filter)
            }}
          >
            {t(`people.only.${filter ?? 'all'}`)}{' '}
            {/* A space, not only a margin: the name a screen reader says runs the two
              together otherwise. */}
            <span className="tabular-nums opacity-70">
              {counts[filter ?? 'all'].toLocaleString('de-DE')}
            </span>
          </Button>
        ))}
      </div>
      {muninns.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-hairline/10 bg-secondary/30 px-4 py-3">
          <p className="min-w-0 flex-1 text-base text-muted-foreground">
            {t('people.standBy.hint', { name })}
          </p>
          <Button
            size="sm"
            disabled={confirmMany.isPending}
            onClick={() => {
              confirmMany.mutate(muninns.map((face) => face.id))
            }}
          >
            {t('people.standBy.button', { count: muninns.length })}
          </Button>
        </div>
      )}
      {faces.isSuccess && all.length === 0 && (
        <p className="mt-4 text-base text-muted-foreground">{t('people.noneToCheck')}</p>
      )}
      <ul className="mt-4 grid grid-cols-4 gap-3 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10">
        {all.map((face) => (
          <li key={face.id} className="relative">
            <button
              type="button"
              aria-label={t('people.checkFace', { name })}
              title={t('people.checkFace', { name })}
              className="mx-auto block rounded-full ring-2 ring-transparent transition hover:ring-accent/60"
              onClick={() => {
                setChecking(face)
              }}
            >
              <Face src={face.crop} size={72} />
            </button>
            {face.assigned_by === 'auto' && (
              <span
                title={t('people.auto')}
                aria-label={t('people.auto')}
                className="absolute -bottom-0.5 -left-0.5 grid size-5 place-items-center rounded-full bg-background text-muted-foreground shadow ring-1 ring-hairline/15"
              >
                <Symbol name="auto_awesome" size={12} />
              </span>
            )}
            <button
              type="button"
              aria-label={t('people.notThem', { name })}
              title={t('people.notThem', { name })}
              disabled={answer.isPending}
              className="absolute -right-0.5 -top-0.5 grid size-6 place-items-center rounded-full bg-background text-muted-foreground shadow ring-1 ring-hairline/15 hover:text-destructive"
              onClick={() => {
                answer.mutate({ faceId: face.id, yes: false })
              }}
            >
              <Symbol name="close" size={14} />
            </button>
          </li>
        ))}
      </ul>
      {faces.hasNextPage && (
        <Button
          variant="outline"
          className="mt-4 w-full"
          disabled={faces.isFetchingNextPage}
          onClick={() => void faces.fetchNextPage()}
        >
          {t('people.more')}
        </Button>
      )}
      {checking && (
        <FaceCheckDialog
          face={checking}
          person={{ id: personId, name }}
          onOpenChange={(open) => {
            if (!open) setChecking(null)
          }}
        />
      )}
    </div>
  )
}

/** "Lena als Kind" and "Lena" are one person: pick the one this becomes. */
function MergeDialog({
  personId,
  name,
  open,
  onOpenChange,
  onMerged,
}: {
  personId: string
  name: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onMerged: (into: string) => void
}) {
  const { t } = useTranslation()
  const people = usePeople()
  const merge = useMerge(personId)
  const others = (people.data?.persons ?? []).filter((person) => person.id !== personId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('people.mergeTitle', { name })}</DialogTitle>
        <DialogDescription>{t('people.mergeText', { name })}</DialogDescription>
        <ul className="mt-4 max-h-80 space-y-1 overflow-y-auto">
          {others.map((person) => (
            <li key={person.id}>
              <button
                type="button"
                disabled={merge.isPending}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-secondary/60"
                onClick={() => {
                  merge.mutate(person.id, {
                    onSuccess: () => {
                      onOpenChange(false)
                      onMerged(person.id)
                    },
                  })
                }}
              >
                <Face src={person.cover?.crop} size={36} />
                <span className="text-md text-foreground">{person.name}</span>
                <span className="ml-auto text-sm text-muted-foreground">
                  {t('people.photos', { count: person.media })}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {others.length === 0 && (
          <p className="mt-4 text-base text-muted-foreground">{t('people.nobodyElse')}</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
