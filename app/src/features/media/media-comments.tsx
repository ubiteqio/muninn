import { useTranslation } from 'react-i18next'

import type { Medium } from '@/features/albums/use-albums'
import { ViewerSheet } from '@/features/media/viewer-sheet'
import { CommentsSection } from '@/features/social/comments'
import { useSocial } from '@/features/social/use-social'

/** The conversation about the picture on screen, in a panel of its own: the speech bubble opens it. */
export function MediaComments({ medium, onClose }: { medium: Medium; onClose: () => void }) {
  const { t } = useTranslation()
  const target = { kind: 'media', id: medium.id } as const
  const count = useSocial(target).data?.comments ?? 0

  return (
    <ViewerSheet
      label={t('comments.title')}
      title={count > 0 ? `${t('comments.title')} · ${String(count)}` : t('comments.title')}
      onClose={onClose}
    >
      <div className="mt-4">
        <CommentsSection target={target} />
      </div>
    </ViewerSheet>
  )
}
