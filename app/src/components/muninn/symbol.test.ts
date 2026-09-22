import { describe, expect, it } from 'vitest'

// Vite hands both of these to the test as plain text, so nothing here needs to touch a disk.
import subsetScript from '../../../scripts/subset-icons.py?raw'

const sources: Record<string, string> = import.meta.glob('/src/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

/**
 * The icon font is cut down to the icons listed in scripts/subset-icons.py. An icon that is used
 * but not listed there has no glyph, and Material Symbols then writes its ligature name out in
 * letters - "chevron_left" spelled across whatever sits next to it. Nothing else catches that.
 */
describe('the icon font', () => {
  it('carries every icon the app names', () => {
    const listed = new Set(
      [...subsetScript.matchAll(/^\s+"([a-z_]+)",$/gm)].map((match) => match[1]),
    )

    const used = new Set(
      Object.values(sources).flatMap((source) =>
        [...source.matchAll(/<Symbol\b[^>]*?\bname="([a-z_]+)"/g)].map((match) => match[1]),
      ),
    )

    expect([...used].filter((icon) => !listed.has(icon))).toEqual([])
  })
})
