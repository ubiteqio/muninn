import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { useMediumDetail } from '@/features/media/use-medium'
import type { FaceView } from '@/features/people/use-people'

/**
 * Which folder the original lies in, and the whole way to it.
 *
 * Two babies are the same face to anybody; the folder they were photographed in is often the
 * only thing that tells them apart. The name alone is what fits on the line, so the way there
 * goes on the mouseover.
 */
function whereItLies(relativePath: string | undefined) {
  if (!relativePath) return null
  const parts = relativePath.split('/').filter(Boolean)
  parts.pop()
  const album = parts.at(-1)
  return album === undefined ? null : { album, path: parts.join('/') }
}

/**
 * The whole photo with one face marked, and the folder it came from. The round crop alone can
 * mislead: a face at the edge of a selfie shows the neighbour beside it larger than itself.
 */
export function FacePhoto({ face }: { face: FaceView }) {
  const { t } = useTranslation()
  const medium = useMediumDetail(face.media_id)
  const data = medium.data
  const where = whereItLies(data?.origin.relative_path)
  // A face from a video was seen at one second; the preview shows another. Then the square
  // of the face itself, large, is the better picture.
  const picture = face.second === null ? (data?.urls.preview ?? data?.urls.thumb) : null

  return (
    <div>
      <div className="relative flex items-center justify-center overflow-hidden rounded-lg bg-black">
        {picture ? (
          <div className="relative">
            <img
              src={picture}
              alt=""
              className="block max-h-[60vh] w-auto max-w-full object-contain"
            />
            <span
              aria-hidden="true"
              className="absolute rounded-md shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] ring-2 ring-accent"
              style={{
                left: `${String(face.box.left * 100)}%`,
                top: `${String(face.box.top * 100)}%`,
                width: `${String((face.box.right - face.box.left) * 100)}%`,
                height: `${String((face.box.bottom - face.box.top) * 100)}%`,
              }}
            />
          </div>
        ) : (
          <img src={face.crop} alt="" className="size-72 object-cover" />
        )}
      </div>
      {where && (
        <p
          className="mt-2 flex items-center gap-1.5 text-sm text-muted-foreground"
          title={where.path}
        >
          <Symbol name="folder" size={16} aria-hidden="true" />
          <span className="sr-only">{t('people.inAlbum')}</span>
          <span className="truncate">{where.album}</span>
        </p>
      )}
    </div>
  )
}
