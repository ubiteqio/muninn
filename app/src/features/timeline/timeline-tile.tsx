import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import type { Medium } from '@/features/albums/use-albums'
import { formatDate } from '@/features/media/format'
import { VideoMark } from '@/features/media/video-mark'

export function TimelineTile({ medium, onOpen }: { medium: Medium; onOpen: () => void }) {
  const { t } = useTranslation()

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t('media.open', { date: formatDate(medium.taken_at) })}
      className="relative aspect-square w-full overflow-hidden bg-secondary/60 transition hover:brightness-110"
    >
      {medium.urls.thumb ? (
        <img
          src={medium.urls.thumb}
          alt=""
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
        />
      ) : (
        // No preview yet: Huginn is still working, and saying so beats an empty tile.
        <span className="flex h-full w-full items-center justify-center text-muted-foreground">
          <Symbol name="history" size={18} />
        </span>
      )}

      {medium.kind === 'video' && <VideoMark seconds={medium.duration_seconds} compact />}
    </button>
  )
}
