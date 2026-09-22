/** "gerade eben", "vor 5 Min.", "vor 3 Std.", "gestern", then the date - how a chat says it. */
export function when(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime()
  const seconds = Math.max(0, Math.round((now - then) / 1000))
  if (seconds < 60) return 'gerade eben'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `vor ${String(minutes)} Min.`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `vor ${String(hours)} Std.`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'gestern'
  if (days < 7) return `vor ${String(days)} Tagen`
  return new Date(iso).toLocaleDateString('de-DE', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
