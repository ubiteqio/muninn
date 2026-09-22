import { describe, expect, it } from 'vitest'

import { pagesAround } from '@/lib/pages'

describe('pagesAround', () => {
  it('shows every page when there are few', () => {
    expect(pagesAround(1, 3)).toEqual([1, 2, 3])
  })

  it('shows the ends and the neighbours of the current page, with gaps between', () => {
    expect(pagesAround(6, 12)).toEqual([1, 'gap', 5, 6, 7, 'gap', 12])
  })

  it('shows a single missing page instead of a gap for it', () => {
    expect(pagesAround(4, 8)).toEqual([1, 2, 3, 4, 5, 'gap', 8])
  })
})
