import { useTranslation } from 'react-i18next'

import { NameDialog } from '@/features/people/name-dialog'
import { useNameFace, usePeople } from '@/features/people/use-people'

/**
 * Say who one face is: a person there is, or a new one. Also the way out of a wrong suggestion,
 * when "no" is not the whole answer.
 */
export function NameFace({
  faceId,
  crop,
  title,
  exclude,
  onDone,
}: {
  faceId: string
  crop: string
  title?: string
  /** The person the face was wrongly taken for. */
  exclude?: string
  onDone: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const people = usePeople()
  const name = useNameFace()
  return (
    <NameDialog
      open
      onOpenChange={onDone}
      title={title ?? t('people.whoIsThis')}
      faces={[{ id: faceId, crop }]}
      persons={people.data?.persons ?? []}
      exclude={exclude}
      pending={name.isPending}
      failed={name.isError}
      onName={(value) => {
        name.mutate(
          { faceId, name: value },
          {
            onSuccess: () => {
              onDone(false)
            },
          },
        )
      }}
    />
  )
}
