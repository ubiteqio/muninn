/**
 * How Muninn writes dates, sizes and running times.
 *
 * German formatting is hard-coded nowhere: the locale comes from the interface language, so the
 * prepared English translation gets English dates without a second implementation.
 */

const LOCALE = 'de-DE'

export function formatDate(taken: string | null): string {
  return taken ? new Date(taken).toLocaleDateString(LOCALE) : ''
}

/** "14. Juli 2009 um 17:30" - what the info panel shows. */
export function formatDateTime(taken: string | null): string {
  if (!taken) return ''
  return new Date(taken).toLocaleString(LOCALE, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "1:04", and "1:02:03" once an hour is full. */
export function formatDuration(seconds: number | null): string {
  if (!seconds) return ''

  const whole = Math.round(seconds)
  const minutes = Math.floor(whole / 60) % 60
  const hours = Math.floor(whole / 3600)
  const rest = String(whole % 60).padStart(2, '0')

  if (hours === 0) return `${String(minutes)}:${rest}`
  return `${String(hours)}:${String(minutes).padStart(2, '0')}:${rest}`
}

/** File sizes as a person reads them: "4,2 MB", "1,1 GB". */
export function formatBytes(bytes: number): string {
  const units = ['B', 'kB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit += 1
  }

  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${value.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${units[unit] ?? 'B'}`
}

/** "45,4372° N, 12,3345° O" - readable, and good enough to paste into a map. */
export function formatCoordinates(latitude: number, longitude: number): string {
  const degrees = (value: number, positive: string, negative: string) =>
    `${Math.abs(value).toLocaleString(LOCALE, { maximumFractionDigits: 4 })}° ${value >= 0 ? positive : negative}`

  return `${degrees(latitude, 'N', 'S')}, ${degrees(longitude, 'O', 'W')}`
}

/** The folder a file lies in, as the NAS spells it. Empty for a file at the very top. */
export function folderOf(relativePath: string): string {
  const cut = relativePath.lastIndexOf('/')
  return cut === -1 ? '' : relativePath.slice(0, cut)
}
