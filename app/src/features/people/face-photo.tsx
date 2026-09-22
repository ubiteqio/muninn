import { useMediumDetail } from '@/features/media/use-medium'
import type { FaceView } from '@/features/people/use-people'

/**
 * The whole photo with one face marked. The round crop alone can mislead: a face at the edge of
 * a selfie shows the neighbour beside it larger than itself.
 */
export function FacePhoto({ face }: { face: FaceView }) {
  const medium = useMediumDetail(face.media_id)
  const data = medium.data
  // A face from a video was seen at one second; the preview shows another. Then the square
  // of the face itself, large, is the better picture.
  const picture = face.second === null ? (data?.urls.preview ?? data?.urls.thumb) : null

  return (
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
  )
}
