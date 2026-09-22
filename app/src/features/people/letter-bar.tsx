import { useTranslation } from 'react-i18next'

import { LETTERS, OTHER } from '@/features/people/letters'
import { cn } from '@/lib/utils'

const PILL =
  'grid h-9 shrink-0 snap-start place-items-center rounded-full text-base font-medium transition disabled:pointer-events-none'

/**
 * "Alle A B C …": the letters names start with. A letter nobody's name starts with stays in its
 * place, faint, so the row never shifts. Up to a laptop's width the row scrolls sideways inside
 * its card; wider, it wraps.
 */
export function LetterBar({
  counts,
  active,
  onChange,
  className,
}: {
  /** How many names start with each letter. */
  counts: Map<string, number>
  /** The letter chosen, or undefined for everybody. */
  active: string | undefined
  onChange: (letter: string | undefined) => void
  className?: string
}) {
  const { t } = useTranslation()

  return (
    <div
      role="group"
      aria-label={t('people.letters')}
      className={cn(
        'scroll-snap-x flex gap-0.5 overflow-x-auto lg:flex-wrap lg:overflow-visible',
        // Narrower than a laptop the row fades out on the right: there is more to swipe to. The padding lets
        // the last letter scroll clear of the fade.
        'pr-8 [mask-image:linear-gradient(to_right,black_calc(100%-2.5rem),transparent)] lg:pr-0 lg:[mask-image:none]',
        className,
      )}
    >
      <button
        type="button"
        aria-pressed={active === undefined}
        className={cn(
          PILL,
          'px-4',
          active === undefined
            ? 'bg-primary text-primary-foreground'
            : 'bg-secondary/50 text-foreground hover:bg-secondary',
        )}
        onClick={() => {
          onChange(undefined)
        }}
      >
        {t('people.allLetters')}
      </button>
      {LETTERS.map((letter) => {
        const count = counts.get(letter) ?? 0
        const chosen = active === letter
        return (
          <button
            key={letter}
            type="button"
            aria-pressed={chosen}
            aria-label={
              letter === OTHER
                ? t('people.otherLetter', { count })
                : t('people.letter', { letter, count })
            }
            title={
              letter === OTHER
                ? t('people.otherLetter', { count })
                : t('people.letter', { letter, count })
            }
            disabled={count === 0}
            className={cn(
              PILL,
              'w-9',
              chosen
                ? 'bg-primary text-primary-foreground'
                : count === 0
                  ? 'text-muted-foreground/35'
                  : 'text-foreground hover:bg-secondary',
            )}
            onClick={() => {
              onChange(chosen ? undefined : letter)
            }}
          >
            {letter}
          </button>
        )
      })}
    </div>
  )
}
