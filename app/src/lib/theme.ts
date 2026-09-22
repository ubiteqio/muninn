/**
 * Light or dark, per device. Rabenschwarz is the design's default; Pergament is the light one;
 * "system" follows the device. Kept in this browser only: a phone at night and a desk by day
 * may well want different ones.
 */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'muninn.theme'
const DARK_BAR = '#0B0D12'
const LIGHT_BAR = '#F5F0E6'

let following: MediaQueryList | null = null
let onSystemChange: (() => void) | null = null

export function storedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'system' ? value : 'dark'
  } catch {
    return 'dark'
  }
}

function systemIsDark(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : true
}

/** Put the chosen look on the page, and keep following the device when that was chosen. */
export function applyTheme(theme: Theme): void {
  const dark = theme === 'dark' || (theme === 'system' && systemIsDark())
  document.documentElement.classList.toggle('dark', dark)
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', dark ? DARK_BAR : LIGHT_BAR)

  if (following && onSystemChange) following.removeEventListener('change', onSystemChange)
  following = null
  onSystemChange = null
  if (theme === 'system' && typeof window.matchMedia === 'function') {
    following = window.matchMedia('(prefers-color-scheme: dark)')
    onSystemChange = () => {
      applyTheme('system')
    }
    following.addEventListener('change', onSystemChange)
  }
}

export function chooseTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // Private window or blocked storage: it still applies, just not for next time.
  }
  applyTheme(theme)
}
