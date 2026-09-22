import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Face } from '@/features/people/face'
import { NameFace } from '@/features/people/name-face'
import { Similarity } from '@/features/people/similarity'
import { type MediaFace, useAnswer, useMediaFaces } from '@/features/people/use-people'

/**
 * Who is in the picture, in the info panel: named people lead to their page, a suggestion is
 * answered right here, and an unknown face can be named on the spot.
 */
export function PeopleInMedium({ mediaId }: { mediaId: string }) {
  const { t } = useTranslation()
  const faces = useMediaFaces(mediaId)
  // Named people first, then the guesses, then the faces nobody knows yet.
  const items = [...(faces.data ?? [])].sort((a, b) => rank(a) - rank(b))
  if (items.length === 0) return null

  return (
    <section className="mt-5" aria-label={t('people.title')}>
      <h3 className="mb-2 text-xs-plus text-muted-foreground">{t('people.title')}</h3>
      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <FaceChip key={item.face.id} item={item} />
        ))}
      </ul>
    </section>
  )
}

function rank(item: MediaFace): number {
  if (item.person) return 0
  return item.suggested ? 1 : 2
}

const CHIP =
  'flex items-center gap-2 rounded-full border border-hairline/10 bg-secondary/40 py-1 pl-1 pr-3 text-base text-foreground'

function FaceChip({ item }: { item: MediaFace }) {
  const { t } = useTranslation()
  const answer = useAnswer()
  const [naming, setNaming] = useState(false)

  if (item.person) {
    const person = item.person
    const name = person.name
    return (
      <li className={`${CHIP} gap-0 pr-0.5`}>
        <Link
          to="/search"
          search={{ q: name }}
          title={t('people.searchFor', { name })}
          className="flex items-center gap-2 rounded-full hover:text-accent"
        >
          <Face src={item.face.crop} size={28} />
          {name}
        </Link>
        <button
          type="button"
          aria-label={t('people.change', { name })}
          title={t('people.change', { name })}
          disabled={answer.isPending}
          className="ml-1.5 grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-secondary hover:text-foreground"
          onClick={() => {
            setNaming(true)
          }}
        >
          <Symbol name="edit" size={15} />
        </button>
        <button
          type="button"
          aria-label={t('people.remove', { name })}
          title={t('people.remove', { name })}
          disabled={answer.isPending}
          className="grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-secondary hover:text-destructive"
          onClick={() => {
            // The face leaves them, is not given to them again, and waits among the unnamed.
            answer.mutate({ faceId: item.face.id, yes: false })
          }}
        >
          <Symbol name="close" size={16} />
        </button>
        {naming && (
          <NameFace
            faceId={item.face.id}
            crop={item.face.crop}
            title={t('people.whoInstead', { name })}
            exclude={person.id}
            onDone={setNaming}
          />
        )}
      </li>
    )
  }

  if (item.suggested) {
    const name = item.suggested.name
    return (
      <li className={CHIP}>
        <button
          type="button"
          title={t('people.someoneElse')}
          className="flex items-center gap-2 rounded-full hover:text-accent"
          onClick={() => {
            setNaming(true)
          }}
        >
          <Face src={item.face.crop} size={28} />
          <span>{t('people.maybe', { name })}</span>
        </button>
        <Similarity value={item.face.suggested_similarity} />
        <button
          type="button"
          aria-label={t('people.yes', { name })}
          disabled={answer.isPending}
          className="grid size-6 place-items-center rounded-full text-accent hover:bg-accent/15"
          onClick={() => {
            answer.mutate({ faceId: item.face.id, yes: true })
          }}
        >
          <Symbol name="check_circle" size={18} />
        </button>
        <button
          type="button"
          aria-label={t('people.no', { name })}
          disabled={answer.isPending}
          className="-mr-1.5 grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-secondary"
          onClick={() => {
            answer.mutate({ faceId: item.face.id, yes: false })
          }}
        >
          <Symbol name="close" size={16} />
        </button>
        {naming && (
          <NameFace
            faceId={item.face.id}
            crop={item.face.crop}
            title={t('people.whoInstead', { name })}
            exclude={item.suggested.id}
            onDone={setNaming}
          />
        )}
      </li>
    )
  }

  return (
    <li>
      <button
        type="button"
        aria-label={t('people.who')}
        title={t('people.who')}
        className={`${CHIP} gap-1 pr-2 text-muted-foreground hover:border-accent/40 hover:text-foreground`}
        onClick={() => {
          setNaming(true)
        }}
      >
        <Face src={item.face.crop} size={28} />
        <Symbol name="question_mark" size={16} />
      </button>
      {naming && <NameFace faceId={item.face.id} crop={item.face.crop} onDone={setNaming} />}
    </li>
  )
}
