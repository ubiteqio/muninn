import type { Medium } from '@/features/albums/use-albums'

/**
 * The signed address of the original, asking for it as a download.
 *
 * The signature covers the medium and the variant, not the query as a whole, so hanging the wish
 * for a download on the end changes nothing about who may load it.
 */
export function downloadAddress(medium: Medium): string {
  return `${medium.urls.original}&download=1`
}

/**
 * Hand the original to the browser.
 *
 * A link it clicks itself, not a request through JavaScript: the browser then shows its own
 * progress, writes straight to disk, and a four gigabyte video never passes through this tab's
 * memory. The link exists for one click and goes again.
 */
export function downloadOriginal(medium: Medium): void {
  const link = document.createElement('a')
  link.href = downloadAddress(medium)
  link.download = medium.origin.filename
  link.rel = 'noopener'

  document.body.append(link)
  link.click()
  link.remove()
}
