import { describe, expect, it } from 'vitest'

// The font's own list, read as text: the script is Python, and this is the one thing in it the
// app depends on.
import subsetScript from '../../../scripts/subset-icons.py?raw'

/**
 * Every icon the app names has to be in the font.
 *
 * The font is a subset: only the icons listed in scripts/subset-icons.py are in it. An icon
 * that is named but missing does not fall back to a blank - the ligature stays unresolved and
 * the browser prints the word itself, so a card wore "CELEBRATION" across its cover in
 * letters. Nothing in the types catches that, which is what this is for.
 */
function iconsInTheFont(): Set<string> {
  const from = subsetScript.indexOf('ICONS = [')
  const list = subsetScript.slice(from, subsetScript.indexOf(']', from))
  return new Set([...list.matchAll(/"([a-z0-9_]+)"/g)].map((found) => found[1] ?? ''))
}

/** Every icon name written out in the source: <Symbol name="…"> and the maps of kinds. */
function iconsInTheSource(): Map<string, string> {
  const sources = import.meta.glob('/src/**/*.{ts,tsx}', {
    query: '?raw',
    import: 'default',
    eager: true,
  })
  const named = new Map<string, string>()

  for (const [path, source] of Object.entries(sources)) {
    if (typeof source !== 'string' || /\.test\.tsx?$/.test(path)) continue

    // Only a Symbol's name is an icon; a field called "password" is not.
    for (const found of source.matchAll(/<Symbol\b[^>]*?\sname="([a-z0-9_]+)"/gs)) {
      named.set(found[1] ?? '', path)
    }
    // The per-kind and per-theme maps: `trip: { icon: 'luggage', … }`, `water: 'pool',`.
    for (const found of source.matchAll(/\bicon: '([a-z0-9_]+)'/g)) {
      named.set(found[1] ?? '', path)
    }
    if (/ICON: Record<string, string>/.test(source)) {
      for (const found of source.matchAll(/^ {2}[a-z]+: '([a-z0-9_]+)',$/gm)) {
        named.set(found[1] ?? '', path)
      }
    }
  }

  return named
}

describe('the icon font', () => {
  it('holds every icon the app asks for', () => {
    const inTheFont = iconsInTheFont()
    const missing = [...iconsInTheSource()]
      .filter(([icon]) => !inTheFont.has(icon))
      .map(([icon, path]) => `${icon} (${path})`)

    expect(missing).toEqual([])
  })

  it('knows what it is reading, or it would pass while finding nothing', () => {
    expect(iconsInTheFont().size).toBeGreaterThan(50)
    expect(iconsInTheSource().size).toBeGreaterThan(20)
  })
})
