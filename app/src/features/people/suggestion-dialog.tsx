import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Face } from '@/features/people/face'
import { FacePhoto } from '@/features/people/face-photo'
import { NameFace } from '@/features/people/name-face'
import { Similarity } from '@/features/people/similarity'
import { type FaceView, useAnswer, usePersonFaces } from '@/features/people/use-people'

/** How many of the person's faces stand beside the question, to compare with. */
const COMPARE = 8

/**
 * "Ist das Lena?", large: the whole photo with the face marked, and faces that are already
 * Lena beside it. A small circle is often not enough to tell two children apart.
 */
export function SuggestionDialog({
  face,
  person,
  open,
  onOpenChange,
}: {
  face: FaceView
  person: { id: string; name: string }
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const known = usePersonFaces(person.id)
  const answer = useAnswer()
  // "Nicht Lena" is sometimes not the whole answer: it is Mia.
  const [other, setOther] = useState(false)
  const compare = (known.data?.pages[0]?.items ?? []).slice(0, COMPARE)
  const decide = (yes: boolean) => {
    answer.mutate(
      { faceId: face.id, yes },
      {
        onSuccess: () => {
          onOpenChange(false)
        },
      },
    )
  }

  if (other) {
    return (
      <NameFace
        faceId={face.id}
        crop={face.crop}
        title={t('people.whoInstead', { name: person.name })}
        exclude={person.id}
        onDone={onOpenChange}
      />
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')} className="max-w-4xl">
        <DialogTitle className="flex flex-wrap items-center gap-2">
          {t('people.isThis', { name: person.name })}
          <Similarity value={face.suggested_similarity} />
        </DialogTitle>
        <DialogDescription>{t('people.compareHint', { name: person.name })}</DialogDescription>

        <div className="mt-4 grid gap-5 md:grid-cols-[1fr_220px]">
          <FacePhoto face={face} />

          <div>
            <h3 className="text-xs-plus text-muted-foreground">
              {t('people.alreadyThem', { name: person.name })}
            </h3>
            <ul className="mt-2 grid grid-cols-4 gap-2 md:grid-cols-3">
              {compare.map((known) => (
                <li key={known.id}>
                  <Face src={known.crop} size={64} />
                </li>
              ))}
            </ul>
            {known.isSuccess && compare.length === 0 && (
              <p className="mt-2 text-base text-muted-foreground">{t('people.noneYet')}</p>
            )}
          </div>
        </div>

        {/* On a phone the answer comes first, Nein and Ja side by side, and "Jemand anderes" below
            across the width; from the tablet on, one row as before. */}
        <div className="mt-5 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
          <Button
            variant="outline"
            className="order-last col-span-2 sm:order-none sm:mr-auto"
            disabled={answer.isPending}
            onClick={() => {
              setOther(true)
            }}
          >
            <Symbol name="person_search" size={18} />
            {t('people.someoneElse')}
          </Button>
          <Button
            aria-label={t('people.notThem', { name: person.name })}
            variant="outline"
            disabled={answer.isPending}
            onClick={() => {
              decide(false)
            }}
          >
            <Symbol name="close" size={18} />
            {/* A phone has room for the answer, not the sentence; the button keeps its name. */}
            <span className="sm:hidden">{t('people.shortNo')}</span>
            <span className="hidden sm:inline">{t('people.notThem', { name: person.name })}</span>
          </Button>
          <Button
            aria-label={t('people.yesThem', { name: person.name })}
            disabled={answer.isPending}
            onClick={() => {
              decide(true)
            }}
          >
            <Symbol name="check_circle" size={18} />
            <span className="sm:hidden">{t('people.shortYes')}</span>
            <span className="hidden sm:inline">{t('people.yesThem', { name: person.name })}</span>
          </Button>
        </div>
        {answer.isError && <p className="mt-2 text-base text-destructive">{t('people.failed')}</p>}
      </DialogContent>
    </Dialog>
  )
}
