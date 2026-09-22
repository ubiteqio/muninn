import { describe, expect, it } from 'vitest'

import { letterOf, OTHER } from '@/features/people/letters'

describe('letterOf', () => {
  it('files a name under its first letter, accents and case aside', () => {
    expect(letterOf('mats')).toBe('M')
    expect(letterOf('Ömer')).toBe('O')
    expect(letterOf('Ärzte')).toBe('A')
    expect(letterOf('Łukasz')).toBe('L')
    expect(letterOf('  Oskar')).toBe('O')
  })

  it('puts everything else under #', () => {
    expect(letterOf('2Pac')).toBe(OTHER)
    expect(letterOf('Ωmega')).toBe(OTHER)
  })
})
