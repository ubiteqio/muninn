import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { LoadingBody, Placeholder } from '@/components/muninn/placeholder'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Face } from '@/features/people/face'
import { usePeople } from '@/features/people/use-people'

/** As many faces as the row ever shows. */
const FACES = 16

/**
 * The persons at the top of the search, as the concept has it: a tap searches for them, and
 * "Alle" leads to the Personen screen. While nobody is named yet, it invites to name the groups.
 *
 * Who there is decides whether the row stands at all, so while the answer is on its way it holds
 * the height it will have: otherwise the hint below would start under the search field and be
 * pushed down a moment later.
 */
export function PeopleRow({ onPerson }: { onPerson: (name: string) => void }) {
  const { t } = useTranslation()
  const people = usePeople()
  const persons = people.data?.persons ?? []
  const groups = people.data?.groups.items.length ?? 0
  const waiting = people.data?.suggestions ?? 0
  if (!people.isPending && persons.length === 0 && groups === 0 && waiting === 0) return null

  return (
    <section aria-labelledby="people-row-heading" aria-busy={people.isPending}>
      <SectionHeading
        id="people-row-heading"
        title={t('people.title')}
        action={
          <Link to="/people" className="text-sm font-medium text-primary hover:text-accent">
            {/* Until the answer is here, the word this link carries in a library with names. */}
            {people.isPending || persons.length > 0 ? t('common.showAll') : t('people.nameThem')}
          </Link>
        }
      />
      {people.isPending ? (
        <PeopleRowLoading />
      ) : persons.length > 0 ? (
        <ul className="mt-3 flex gap-4 overflow-x-auto pb-1">
          {persons.slice(0, FACES).map((person) => (
            <li key={person.id} className="shrink-0">
              <button
                type="button"
                className="group flex w-[72px] flex-col items-center gap-1.5"
                onClick={() => {
                  onPerson(person.name)
                }}
              >
                <Face
                  src={person.cover?.crop}
                  size={60}
                  className="ring-2 ring-transparent transition group-hover:ring-accent/60"
                />
                <span className="w-full truncate text-center text-sm text-foreground">
                  {person.name}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-base text-muted-foreground">
          {t('people.waitingNames', { count: groups })}
        </p>
      )}
    </section>
  )
}

/**
 * The faces on their way, in the size and at the pitch they will have. The row carries no frame
 * of its own, so the shapes stand as bare as the faces do rather than in a box that then goes.
 */
function PeopleRowLoading() {
  return (
    <LoadingBody boxed={false} className="mt-3 flex gap-4 overflow-hidden pb-1">
      {Array.from({ length: FACES }, (_, index) => (
        <div key={index} className="flex w-[72px] shrink-0 flex-col items-center gap-1.5">
          <Placeholder className="size-[60px] rounded-full" />
          <Placeholder className="h-4 w-14" />
        </div>
      ))}
    </LoadingBody>
  )
}
