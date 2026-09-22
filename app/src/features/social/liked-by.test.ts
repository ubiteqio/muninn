import { describe, expect, it } from 'vitest'

import { likedBy } from '@/features/social/liked-by'

const t = ((key: string, values?: Record<string, unknown>) => {
  const texts: Record<string, string> = {
    'social.you': 'dir',
    'social.and': 'und',
    'social.likedBy': `Gefällt ${String(values?.names)}`,
    'social.likedByMore': `Gefällt ${String(values?.names)} und ${String(values?.count)} weiteren`,
    'social.reactedByMore': `${String(values?.names)} und ${String(values?.count)} weitere`,
  }
  return texts[key] ?? key
}) as never

describe('who likes it, in words', () => {
  it.each([
    [{ likes: 1, liked: true, likers: ['Boris'], favorite: false, comments: 0 }, 'Gefällt dir'],
    [
      { likes: 2, liked: false, likers: ['Anna', 'Boris'], favorite: false, comments: 0 },
      'Gefällt Anna und Boris',
    ],
    [
      { likes: 2, liked: true, likers: ['Boris', 'Anna'], favorite: false, comments: 0 },
      'Gefällt dir und Anna',
    ],
    [
      { likes: 5, liked: true, likers: ['Boris', 'Anna', 'Lena'], favorite: false, comments: 0 },
      'Gefällt dir, Anna, Lena und 2 weiteren',
    ],
    [{ likes: 0, liked: false, likers: [], favorite: false, comments: 0 }, ''],
  ])('%j', (social, said) => {
    expect(likedBy({ ...social, reactions: [], people: [] }, t)).toBe(said)
  })

  it('names each reaction when asked to', () => {
    const social = {
      likes: 4,
      liked: true,
      likers: ['Boris', 'Anna', 'Lena'],
      favorite: false,
      comments: 0,
      reaction: 'joy' as const,
      reactions: [],
      people: [
        { name: 'Boris', reaction: 'joy' as const },
        { name: 'Anna', reaction: 'heart' as const },
        { name: 'Lena', reaction: 'hang_loose' as const },
      ],
    }

    expect(likedBy(social, t, { reactions: true })).toBe('dir 😂, Anna ❤️, Lena 🤙 und 1 weitere')
  })
})
