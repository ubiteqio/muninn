import { useTranslation } from 'react-i18next'

import type { Happening } from '@/features/notify/use-notifications'
import { emojiOf } from '@/features/social/reactions'

/** A heart is a like; any other reaction is told by its emoji. */
export function reactedWith(item: Happening): string | null {
  return item.kind === 'like' && item.reaction && item.reaction !== 'heart' ? item.reaction : null
}

/** "hat kommentiert", "hat mit 😂 reagiert", "12 neue Medien". */
export function useHappeningText(item: Happening): string {
  const { t } = useTranslation()
  const reaction = reactedWith(item)
  if (item.kind === 'new_media') return t('activity.kind.new_media', { count: item.count })
  if (reaction) return t('activity.kind.reaction', { emoji: emojiOf(reaction) })
  return t(`activity.kind.${item.kind}`)
}
