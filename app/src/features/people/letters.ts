/** Everything that does not start with a letter from A to Z. */
export const OTHER = '#'

export const LETTERS = [...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i)), OTHER]

/** Where a name is filed: Ärzte under A, Łukasz under L, 2Pac under #. */
export function letterOf(name: string): string {
  const first = name.trim().normalize('NFD').replace(/[̀-ͯ]/g, '').charAt(0).toUpperCase()
  const plain = first === 'Ł' ? 'L' : first === 'Ø' ? 'O' : first === 'ß' ? 'S' : first
  return /^[A-Z]$/.test(plain) ? plain : OTHER
}
