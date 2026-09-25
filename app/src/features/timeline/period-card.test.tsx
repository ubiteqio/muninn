import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PeriodCard } from '@/features/timeline/period-card'
import type { Period } from '@/features/timeline/use-timeline'

function aPeriod(howMany: number): Period {
  return {
    key: '2017-12',
    start: '2017-12-01',
    count: 120,
    covers: Array.from({ length: howMany }, (_, index) => ({
      id: `cover-${String(index)}`,
      thumb: `/api/v1/media/cover-${String(index)}/thumb?token=a`,
    })),
  } as Period
}

function mosaicOf(covers: number): HTMLElement {
  render(<PeriodCard period={aPeriod(covers)} label="Dezember 2017" onOpen={() => undefined} />)
  // The mosaic sits inside the frame that says this is something holding pictures.
  const square = screen.getByRole('button').querySelector('.grid')
  expect(square).toBeInstanceOf(HTMLElement)
  return square as HTMLElement
}

describe('the mosaic of a period', () => {
  it('divides the square itself rather than letting the pictures divide it', () => {
    // Four thumbnails of four different shapes: with the rows unnamed each one is as tall as
    // the photograph that landed in it, and the card comes out lopsided.
    const square = mosaicOf(4)

    expect(square.className).toContain('grid-cols-2')
    expect(square.className).toContain('grid-rows-2')
    // The square is the frame's now; the mosaic fills it.
    expect(square.className).toContain('h-full')
  })

  it('gives the first of three the whole left half', () => {
    const square = mosaicOf(3)
    const pictures = square.querySelectorAll('img')

    expect(square.className).toContain('grid-rows-2')
    expect(pictures[0]?.className).toContain('row-span-2')
    expect(pictures[1]?.className).not.toContain('row-span-2')
  })

  it('lays two side by side, in one row, without a second one standing empty', () => {
    const square = mosaicOf(2)

    expect(square.className).toContain('grid-cols-2')
    expect(square.className).not.toContain('grid-rows-2')
  })

  it('gives a single picture the whole square', () => {
    const square = mosaicOf(1)

    expect(square.className).not.toContain('grid-cols-2')
    expect(square.querySelectorAll('img')).toHaveLength(1)
  })
})
