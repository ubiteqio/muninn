import { describe, expect, it } from 'vitest'

import { albumRoute, type AlbumSearch, homeRoute, type HomeSearch } from '@/routes/index'

/** What the router hands the validator after it has decoded the query string. */
function validateHome(search: Record<string, unknown>): HomeSearch {
  const validate = homeRoute.options.validateSearch as (
    input: Record<string, unknown>,
  ) => HomeSearch
  return validate(search)
}

function validateAlbum(search: Record<string, unknown>): AlbumSearch {
  const validate = albumRoute.options.validateSearch as (
    input: Record<string, unknown>,
  ) => AlbumSearch
  return validate(search)
}

describe('what the address is allowed to say', () => {
  it('reads a year as text, though a query string makes it a number', () => {
    // "?at=2014" decodes to the number 2014, and a year that is a number breaks every
    // component that treats it as the text it is.
    expect(validateHome({ view: 'months', at: 2014 })).toEqual({ view: 'months', at: '2014' })
  })

  it('keeps a month as it is', () => {
    expect(validateHome({ view: 'days', at: '2014-08' })).toEqual({ view: 'days', at: '2014-08' })
  })

  it('drops a level nobody offers', () => {
    expect(validateHome({ view: 'centuries' })).toEqual({})
  })

  it('passes nothing on when nothing was asked for', () => {
    expect(validateHome({})).toEqual({})
  })

  it('reads the album page the same way', () => {
    expect(validateAlbum({ cursor: 42, medium: 'media-1' })).toEqual({
      cursor: '42',
      medium: 'media-1',
    })
  })
})
