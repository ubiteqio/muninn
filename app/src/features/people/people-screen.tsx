import { Link, useNavigate } from '@tanstack/react-router'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageHeading } from '@/components/layout/page-heading'
import { EmptyNote } from '@/components/muninn/empty-note'
import { Pagination } from '@/components/muninn/pagination'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Face } from '@/features/people/face'
import { LetterBar } from '@/features/people/letter-bar'
import { letterOf } from '@/features/people/letters'
import { NameDialog } from '@/features/people/name-dialog'
import { NameFace } from '@/features/people/name-face'
import { Similarity } from '@/features/people/similarity'
import { SuggestionDialog } from '@/features/people/suggestion-dialog'
import {
  type FaceView,
  type GroupView,
  type PersonView,
  useAnswer,
  useGroupFaces,
  useGroups,
  useNameGroup,
  usePeople,
  useSuggestions,
} from '@/features/people/use-people'
import { cn } from '@/lib/utils'

/**
 * Personen: who is in the photos. Suggestions to answer with one tap, the persons there are,
 * and groups of faces nobody has named yet - naming one names every face in it.
 */
export function PeopleScreen({ letter, page = 1 }: PeopleSearch = {}) {
  const { t } = useTranslation()
  const [showHidden, setShowHidden] = useState(false)
  const navigate = useNavigate()
  const sectionRef = useRef<HTMLElement>(null)
  const people = usePeople(showHidden)
  const groups = useGroups()
  const waiting = people.data?.suggestions ?? 0
  const suggestions = useSuggestions(waiting > 0)
  const persons = useMemo(() => people.data?.persons ?? [], [people.data])
  const browsed = useMemo(() => browse(persons, letter, page), [persons, letter, page])
  // Letter and page live in the address: back from a person lands on the same page.
  const choose = (next: PeopleSearch) => {
    void navigate({ to: '/people', search: next, replace: true })
  }
  const turnTo = (next: number) => {
    choose({ ...(letter === undefined ? {} : { letter }), ...(next > 1 ? { page: next } : {}) })
    // The arrows sit under the faces: the new page starts at the top of the section.
    const top = sectionRef.current?.getBoundingClientRect().top ?? 0
    if (top < 0) sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const allGroups = groups.data?.pages.flatMap((page) => page.items) ?? []
  const allSuggestions = suggestions.data?.pages.flatMap((page) => page.items) ?? []
  const nothing =
    people.isSuccess && persons.length === 0 && allGroups.length === 0 && waiting === 0

  return (
    <AppShell title={t('people.title')} active="people">
      <div className="space-y-8 px-5 md:px-0">
        <PageHeading title={t('people.title')} description={t('people.description')} />
        {people.isError && (
          <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}
        {nothing && <EmptyNote>{t('people.empty')}</EmptyNote>}

        {(persons.length > 0 || showHidden) && (
          <section ref={sectionRef} aria-labelledby="persons-heading" className="scroll-mt-4">
            <SectionHeading
              id="persons-heading"
              title={t(showHidden ? 'people.hiddenTitle' : 'people.persons')}
            />
            <div className="mt-3 flex flex-col gap-1 rounded-lg border border-hairline/10 bg-card p-1.5 lg:flex-row lg:items-center lg:gap-2">
              <LetterBar
                className="min-w-0 flex-1"
                counts={browsed.counts}
                active={letter}
                onChange={(next) => {
                  choose(next === undefined ? {} : { letter: next })
                }}
              />
              <div
                aria-hidden="true"
                className="h-px bg-hairline/10 lg:h-7 lg:w-px lg:self-center"
              />
              <div className="flex items-center justify-between gap-2 pl-2 lg:contents">
                <span className="text-sm tabular-nums text-muted-foreground lg:hidden">
                  {t('people.count', { count: persons.length })}
                </span>
                <button
                  type="button"
                  aria-pressed={showHidden}
                  className={cn(
                    'flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-base font-medium transition',
                    showHidden
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                  )}
                  onClick={() => {
                    setShowHidden(!showHidden)
                    choose({})
                  }}
                >
                  <Symbol name="visibility_off" size={18} />
                  {t('people.hiddenToggle')}
                </button>
              </div>
            </div>
            <ul className="mt-5 grid grid-cols-3 gap-x-3 gap-y-6 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7">
              {browsed.shown.map((person) => (
                <PersonTile key={person.id} person={person} />
              ))}
            </ul>
            {browsed.total > 0 && (
              <div className="mt-6 flex flex-col-reverse items-center gap-3 sm:flex-row sm:justify-between">
                <p className="text-sm tabular-nums text-muted-foreground">
                  {t('people.range', {
                    from: browsed.from,
                    to: browsed.to,
                    count: browsed.total,
                  })}
                </p>
                <Pagination page={browsed.page} pages={browsed.pages} onPage={turnTo} />
              </div>
            )}
            {showHidden && persons.length === 0 && (
              <p className="mt-3 text-base text-muted-foreground">{t('people.noneHidden')}</p>
            )}
          </section>
        )}

        {allSuggestions.length > 0 && (
          <section aria-labelledby="suggestions-heading">
            <SectionHeading
              id="suggestions-heading"
              title={t('people.suggestions', { count: waiting })}
            />
            <ul className="mt-3 flex gap-3 overflow-x-auto pb-1">
              {allSuggestions.map((item) => (
                <SuggestionCard key={item.face.id} face={item.face} person={item.person} />
              ))}
            </ul>
          </section>
        )}

        {allGroups.length > 0 && (
          <section aria-labelledby="groups-heading">
            <SectionHeading id="groups-heading" title={t('people.groups')} />
            <p className="mt-1 text-base text-muted-foreground">{t('people.groupsHint')}</p>
            <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {allGroups.map((group) => (
                <GroupTile key={group.cluster} group={group} persons={persons} />
              ))}
            </ul>
            {groups.hasNextPage && (
              <Button
                variant="outline"
                className="mt-4 w-full"
                disabled={groups.isFetchingNextPage}
                onClick={() => void groups.fetchNextPage()}
              >
                {t('people.more')}
              </Button>
            )}
          </section>
        )}
      </div>
    </AppShell>
  )
}

/** Faces on one page: two rows of seven on a wide screen. */
const PER_PAGE = 14

export interface PeopleSearch {
  /** Only names starting with this letter, or "#" for the rest. */
  letter?: string
  page?: number
}

/**
 * The persons to show: the most photographed first, those of one letter if one is chosen, and
 * of them one page. A page beyond the last, left over in the address, becomes the last.
 */
function browse(persons: PersonView[], letter: string | undefined, page: number) {
  const sorted = [...persons].sort(
    (a, b) => b.media - a.media || a.name.localeCompare(b.name, 'de'),
  )
  const counts = new Map<string, number>()
  for (const person of sorted) {
    const first = letterOf(person.name)
    counts.set(first, (counts.get(first) ?? 0) + 1)
  }
  const matching =
    letter === undefined ? sorted : sorted.filter((person) => letterOf(person.name) === letter)
  const pages = Math.max(1, Math.ceil(matching.length / PER_PAGE))
  const current = Math.min(Math.max(1, Math.floor(page)), pages)
  const start = (current - 1) * PER_PAGE
  const shown = matching.slice(start, start + PER_PAGE)
  return {
    counts,
    shown,
    page: current,
    pages,
    total: matching.length,
    from: start + 1,
    to: start + shown.length,
  }
}

function SuggestionCard({
  face,
  person,
}: {
  face: FaceView
  person: { id: string; name: string }
}) {
  const { t } = useTranslation()
  const answer = useAnswer()
  const [looking, setLooking] = useState(false)
  const [other, setOther] = useState(false)
  const faceId = face.id
  const name = person.name
  return (
    <li>
      <Card className="flex w-[168px] flex-col items-center gap-2 p-3 text-center">
        <button
          type="button"
          aria-label={t('people.lookCloser', { name })}
          title={t('people.lookCloser', { name })}
          className="rounded-full ring-2 ring-transparent transition hover:ring-accent/60"
          onClick={() => {
            setLooking(true)
          }}
        >
          <Face src={face.crop} size={88} />
        </button>
        {looking && <SuggestionDialog face={face} person={person} open onOpenChange={setLooking} />}
        {other && (
          <NameFace
            faceId={faceId}
            crop={face.crop}
            title={t('people.whoInstead', { name })}
            exclude={person.id}
            onDone={setOther}
          />
        )}
        <p className="text-base text-foreground">{t('people.isThis', { name })}</p>
        <Similarity value={face.suggested_similarity} />
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            aria-label={t('people.no', { name })}
            disabled={answer.isPending}
            onClick={() => {
              answer.mutate({ faceId, yes: false })
            }}
          >
            <Symbol name="close" size={18} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            aria-label={t('people.someoneElse')}
            title={t('people.someoneElse')}
            disabled={answer.isPending}
            onClick={() => {
              setOther(true)
            }}
          >
            <Symbol name="person_search" size={18} />
          </Button>
          <Button
            size="sm"
            aria-label={t('people.yes', { name })}
            disabled={answer.isPending}
            onClick={() => {
              answer.mutate({ faceId, yes: true })
            }}
          >
            <Symbol name="check_circle" size={18} />
          </Button>
        </div>
      </Card>
    </li>
  )
}

function PersonTile({ person }: { person: PersonView }) {
  const { t } = useTranslation()
  return (
    <li>
      <Link
        to="/people/$personId"
        params={{ personId: person.id }}
        className="group flex flex-col items-center gap-2 text-center"
      >
        <Face
          src={person.cover?.crop}
          size={88}
          className="ring-2 ring-transparent transition group-hover:ring-accent/60"
        />
        <span className="w-full truncate text-base font-medium text-foreground">{person.name}</span>
        <span className="-mt-1.5 text-sm text-muted-foreground">
          {t('people.photos', { count: person.media })}
        </span>
      </Link>
    </li>
  )
}

/** An unnamed group: four of its faces, and a tap to say who it is. */
function GroupTile({ group, persons }: { group: GroupView; persons: PersonView[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const name = useNameGroup()
  const all = useGroupFaces(open ? group.cluster : null)
  const four = group.faces.slice(0, 4)

  return (
    <li>
      <button
        type="button"
        aria-label={t('people.whoIs', { count: group.size })}
        className="group w-full rounded-lg border border-hairline/10 bg-card p-2 text-left transition hover:border-accent/40"
        onClick={() => {
          setOpen(true)
        }}
      >
        <span className="grid aspect-square grid-cols-2 gap-1 overflow-hidden rounded-md">
          {four.map((face, index) => (
            <span
              key={face.id}
              className={cn(
                'block overflow-hidden bg-secondary',
                four.length === 1 && 'col-span-2 row-span-2',
                four.length === 3 && index === 0 && 'row-span-2',
              )}
            >
              <img src={face.crop} alt="" loading="lazy" className="size-full object-cover" />
            </span>
          ))}
        </span>
        <span className="mt-2 block text-sm text-muted-foreground">
          {t('people.faces', { count: group.size })}
        </span>
      </button>
      {open && (
        <NameDialog
          open={open}
          onOpenChange={setOpen}
          title={t('people.whoIsThis')}
          faces={(all.data ?? group.faces).map((face) => ({ id: face.id, crop: face.crop }))}
          persons={persons}
          pending={name.isPending}
          failed={name.isError}
          onName={(value) => {
            name.mutate(
              { cluster: group.cluster, name: value },
              {
                onSuccess: () => {
                  setOpen(false)
                },
              },
            )
          }}
        />
      )}
    </li>
  )
}
