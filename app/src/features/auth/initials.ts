/** First letters of the display name, at most two: "Anna Bauer" becomes "AB". */
export function initialsOf(displayName: string): string {
  const letters = displayName
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0] ?? '')
    .join('')
  return letters.slice(0, 2).toUpperCase() || '?'
}
