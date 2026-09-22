import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Face } from '@/features/people/face'
import type { PersonView } from '@/features/people/use-people'

/**
 * "Wer ist das?": a name for a face or a group. The persons there are stand ready to pick with
 * one tap, and typing narrows them, so a new group joins Lena instead of becoming a second Lena.
 * A name nobody has yet makes a new person.
 */
export function NameDialog({
  open,
  onOpenChange,
  title,
  faces,
  persons,
  initial = '',
  pending,
  failed,
  onName,
  extra,
  exclude,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  /** The faces this is about, to look at while naming. */
  faces: { id: string; crop: string }[]
  persons: PersonView[]
  initial?: string
  pending: boolean
  failed: boolean
  onName: (name: string) => void
  /** Further actions under the field, like hiding a stranger. */
  extra?: ReactNode
  /** A person not to offer: the one just said to be wrong. */
  exclude?: string | undefined
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial)
  const typed = name.trim().toLowerCase()
  const offered = persons.filter((person) => person.id !== exclude)
  const matches = offered.filter((person) => person.name.toLowerCase().includes(typed))
  const isNew =
    typed.length > 0 &&
    offered.length > 0 &&
    !persons.some((person) => person.name.toLowerCase() === typed)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')} className="text-foreground">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>
          {t(persons.length > 0 ? 'people.pickHint' : 'people.nameHint')}
        </DialogDescription>

        {faces.length > 0 && (
          <ul className="mt-4 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
            {faces.map((face) => (
              <li key={face.id}>
                <Face src={face.crop} size={56} />
              </li>
            ))}
          </ul>
        )}

        <form
          className="mt-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) onName(name.trim())
          }}
        >
          <Input
            autoFocus
            value={name}
            maxLength={80}
            placeholder={t('people.namePlaceholder')}
            aria-label={t('people.name')}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
          {isNew && (
            <p className="mt-2 text-base text-muted-foreground">
              {t('people.newPerson', { name: name.trim() })}
            </p>
          )}
          {matches.length > 0 && (
            <>
              <h3 className="mt-4 text-xs-plus text-muted-foreground">{t('people.known')}</h3>
              <ul
                className="mt-1 max-h-56 space-y-0.5 overflow-y-auto"
                aria-label={t('people.known')}
              >
                {matches.map((person) => (
                  <li key={person.id}>
                    <button
                      type="button"
                      disabled={pending}
                      className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-secondary/60 disabled:opacity-50"
                      onClick={() => {
                        onName(person.name)
                      }}
                    >
                      <Face src={person.cover?.crop} size={32} />
                      <span className="text-md text-foreground">{person.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {failed && <p className="mt-2 text-base text-destructive">{t('people.failed')}</p>}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
            <div>{extra}</div>
            <Button type="submit" disabled={pending || !name.trim()}>
              {t('people.save')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
