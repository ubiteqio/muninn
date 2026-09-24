import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Face } from '@/features/people/face'
import { useAlikeFaces, useDecideAlike } from '@/features/people/use-people'
import { cn } from '@/lib/utils'

/** Where the line sits when nobody has moved it: inside "the same person, another photo". */
const DEFAULT_FROM = 80
/**
 * The server never offers below this, so the slider cannot ask for more than there is.
 *
 * As far down as a suggestion reaches: a face Muninn would ask about is one it can offer
 * here. Higher than that and the slider ran out of travel before it ran out of faces - one
 * picture at the bottom of the range and no way to look further.
 */
const LOWEST = 40
const HIGHEST = 95
const REMEMBERED = 'muninn.alike.from'

function remembered(): number {
  try {
    const kept = Number(localStorage.getItem(REMEMBERED))
    return kept >= LOWEST && kept <= HIGHEST ? kept : DEFAULT_FROM
  } catch {
    return DEFAULT_FROM
  }
}

/**
 * "Auch diese?": after a yes or a no, the same answer for the faces that look the same.
 *
 * The list is asked for once, at the widest distance the server offers, and the slider narrows
 * it here - so moving it costs nothing and you see what each line would take with it before you
 * commit to any of them. Nothing is offered when nothing is close: the dialog closes itself.
 */
export function AlikeDialog({
  faceId,
  person,
  yes,
  onDone,
}: {
  faceId: string
  person: { id: string; name: string }
  yes: boolean
  onDone: () => void
}) {
  const { t } = useTranslation()
  const alike = useAlikeFaces(faceId, person.id)
  const decide = useDecideAlike()
  const [from, setFrom] = useState(remembered)
  const [skipped, setSkipped] = useState<string[]>([])

  const items = alike.data?.items ?? []
  // Nothing alike is the common case, and a question that failed is not worth a dialog either:
  // the one answer has already gone through. Neither must cost a click to dismiss.
  const nothing = !alike.isPending && (alike.isError || items.length === 0)

  useEffect(() => {
    if (nothing) onDone()
  }, [nothing, onDone])

  if (alike.isPending || nothing) return null

  const above = items.filter((item) => Math.round(item.similarity * 100) >= from)
  const chosen = above.filter((item) => !skipped.includes(item.face.id))

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onDone()
      }}
    >
      <DialogContent closeLabel={t('common.close')} className="text-foreground">
        <DialogTitle>
          {t(yes ? 'people.alike.titleYes' : 'people.alike.titleNo', { name: person.name })}
        </DialogTitle>
        <DialogDescription>{t('people.alike.hint')}</DialogDescription>

        <label className="mt-4 block text-sm text-muted-foreground" htmlFor="alike-from">
          {t('people.alike.threshold', { percent: from })}
        </label>
        <input
          id="alike-from"
          type="range"
          min={LOWEST}
          max={HIGHEST}
          step={1}
          value={from}
          aria-label={t('people.alike.threshold', { percent: from })}
          className="mt-1 w-full accent-accent"
          onChange={(event) => {
            const next = Number(event.target.value)
            setFrom(next)
            try {
              localStorage.setItem(REMEMBERED, String(next))
            } catch {
              // A browser that keeps nothing is no reason not to answer the question.
            }
          }}
        />
        <p className="mt-1 text-sm text-muted-foreground">
          {t('people.alike.count', { count: chosen.length })}
        </p>

        <ul className="mt-3 flex max-h-56 flex-wrap gap-2 overflow-y-auto">
          {above.map((item) => {
            const taken = !skipped.includes(item.face.id)
            return (
              <li key={item.face.id}>
                <button
                  type="button"
                  aria-pressed={taken}
                  aria-label={t('people.alike.toggle', {
                    percent: Math.round(item.similarity * 100),
                  })}
                  className={cn(
                    'relative rounded-full ring-2 transition',
                    taken ? 'ring-accent' : 'opacity-40 ring-transparent',
                  )}
                  onClick={() => {
                    setSkipped((before) =>
                      before.includes(item.face.id)
                        ? before.filter((one) => one !== item.face.id)
                        : [...before, item.face.id],
                    )
                  }}
                >
                  <Face src={item.face.crop} size={56} />
                  <span className="absolute inset-x-0 -bottom-1 text-center text-xs tabular-nums text-muted-foreground">
                    {Math.round(item.similarity * 100)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onDone} disabled={decide.isPending}>
            {t('people.alike.later')}
          </Button>
          <Button
            disabled={decide.isPending || chosen.length === 0}
            onClick={() => {
              decide.mutate(
                {
                  personId: person.id,
                  faceIds: chosen.map((item) => item.face.id),
                  yes,
                },
                { onSuccess: onDone },
              )
            }}
          >
            {t('people.alike.apply', { count: chosen.length })}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
