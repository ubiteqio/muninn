import type { useTranslation } from 'react-i18next'

import { emojiOf } from '@/features/social/reactions'
import type { Social } from '@/features/social/use-social'

type Translate = ReturnType<typeof useTranslation>['t']

/**
 * "Gefällt dir", "Gefällt Anna und Boris", "Gefällt dir, Anna und 3 weiteren" - and with
 * ``reactions``, each name with how they reacted: "Anna 😂, Boris ❤️".
 */
export function likedBy(social: Social, t: Translate, { reactions = false } = {}): string {
  if (social.likes === 0) return ''
  const names = social.likers.map((name, index) => {
    const who = index === 0 && social.liked ? t('social.you') : name
    const reaction = social.people[index]?.reaction
    return reactions && reaction ? `${who} ${emojiOf(reaction)}` : who
  })
  if (reactions) {
    const others = social.likes - names.length
    return others > 0
      ? t('social.reactedByMore', { names: names.join(', '), count: others })
      : t('social.reactedBy', { names: names.join(', ') })
  }
  const others = social.likes - names.length
  if (others > 0) {
    return t('social.likedByMore', { names: names.join(', '), count: others })
  }
  if (names.length === 1) return t('social.likedBy', { names: names[0] })
  return t('social.likedBy', {
    names: `${names.slice(0, -1).join(', ')} ${t('social.and')} ${names.at(-1) ?? ''}`,
  })
}
