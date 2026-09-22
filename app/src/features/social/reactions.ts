import type { components } from '@/api/generated/schema'

export type Reaction = components['schemas']['Reaction']

/** The reactions on offer, in the order the row shows them. The server only knows the names. */
export const REACTIONS: readonly { key: Reaction; emoji: string }[] = [
  { key: 'heart', emoji: '❤️' },
  { key: 'thumbs_up', emoji: '👍' },
  { key: 'joy', emoji: '😂' },
  { key: 'wow', emoji: '😮' },
  { key: 'moved', emoji: '🥹' },
  { key: 'clap', emoji: '👏' },
  { key: 'fire', emoji: '🔥' },
  { key: 'hang_loose', emoji: '🤙' },
]

const EMOJI = new Map(REACTIONS.map((reaction) => [reaction.key, reaction.emoji]))

export function emojiOf(reaction: string | null | undefined): string {
  return (reaction && EMOJI.get(reaction as Reaction)) ?? '❤️'
}
