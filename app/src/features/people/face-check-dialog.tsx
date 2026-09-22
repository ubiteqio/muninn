import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { FacePhoto } from '@/features/people/face-photo'
import { NameFace } from '@/features/people/name-face'
import { type FaceView, useAnswer } from '@/features/people/use-people'

/**
 * One of a person's faces, checked on the whole photo: right, not them, or somebody else.
 */
export function FaceCheckDialog({
  face,
  person,
  onOpenChange,
}: {
  face: FaceView
  person: { id: string; name: string }
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const answer = useAnswer()
  const [other, setOther] = useState(false)
  const name = person.name

  if (other) {
    return (
      <NameFace
        faceId={face.id}
        crop={face.crop}
        title={t('people.whoInstead', { name })}
        exclude={person.id}
        onDone={onOpenChange}
      />
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t('common.close')} className="max-w-3xl">
        <DialogTitle>{t('people.isThis', { name })}</DialogTitle>
        <DialogDescription>
          {t(face.assigned_by === 'auto' ? 'people.givenByMuninn' : 'people.givenByHand', { name })}
        </DialogDescription>
        <div className="mt-4">
          <FacePhoto face={face} />
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
            aria-label={t('people.notThem', { name })}
            variant="outline"
            disabled={answer.isPending}
            onClick={() => {
              answer.mutate(
                { faceId: face.id, yes: false },
                {
                  onSuccess: () => {
                    onOpenChange(false)
                  },
                },
              )
            }}
          >
            <Symbol name="close" size={18} />
            {/* A phone has room for the answer, not the sentence; the button keeps its name. */}
            <span className="sm:hidden">{t('people.shortNo')}</span>
            <span className="hidden sm:inline">{t('people.notThem', { name })}</span>
          </Button>
          <Button
            aria-label={t('people.yesThem', { name })}
            disabled={answer.isPending}
            onClick={() => {
              // Confirmed, Muninn's guess becomes a face that vouches for the person.
              if (face.assigned_by !== 'auto') {
                onOpenChange(false)
                return
              }
              answer.mutate(
                { faceId: face.id, yes: true },
                {
                  onSuccess: () => {
                    onOpenChange(false)
                  },
                },
              )
            }}
          >
            <Symbol name="check_circle" size={18} />
            <span className="sm:hidden">{t('people.shortYes')}</span>
            <span className="hidden sm:inline">{t('people.yesThem', { name })}</span>
          </Button>
        </div>
        {answer.isError && <p className="mt-2 text-base text-destructive">{t('people.failed')}</p>}
      </DialogContent>
    </Dialog>
  )
}
