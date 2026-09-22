import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Face } from '@/features/people/face'
import { usePeople } from '@/features/people/use-people'

/**
 * The persons at the top of the search, as the concept has it: a tap searches for them, and
 * "Alle" leads to the Personen screen. While nobody is named yet, it invites to name the groups.
 */
export function PeopleRow({ onPerson }: { onPerson: (name: string) => void }) {
  const { t } = useTranslation()
  const people = usePeople()
  const persons = people.data?.persons ?? []
  const groups = people.data?.groups.items.length ?? 0
  const waiting = people.data?.suggestions ?? 0
  if (persons.length === 0 && groups === 0 && waiting === 0) return null

  return (
    <section aria-labelledby="people-row-heading">
      <SectionHeading
        title={t('people.title')}
        action={
          <Link to="/people" className="text-sm font-medium text-primary hover:text-accent">
            {persons.length > 0 ? t('common.showAll') : t('people.nameThem')}
          </Link>
        }
      />
      {persons.length > 0 ? (
        <ul className="mt-3 flex gap-4 overflow-x-auto pb-1">
          {persons.slice(0, 16).map((person) => (
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
