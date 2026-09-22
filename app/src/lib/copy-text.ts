/**
 * Put text on the clipboard - also where the Clipboard API is missing.
 *
 * Browsers offer navigator.clipboard only in a secure context: HTTPS, or localhost. Muninn at
 * home runs on plain HTTP at a LAN address, where it does not exist. The old way still works
 * there: a hidden text field, selected, and the copy command.
 */
export async function copyText(text: string): Promise<boolean> {
  // The types promise a clipboard; outside a secure context the browser has none.
  if (window.isSecureContext && 'clipboard' in navigator) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Refused (no permission, not focused): try the old way below.
    }
  }

  const field = document.createElement('textarea')
  field.value = text
  field.setAttribute('readonly', '')
  field.style.position = 'fixed'
  field.style.opacity = '0'
  field.style.pointerEvents = 'none'
  document.body.append(field)
  field.select()
  field.setSelectionRange(0, text.length)
  let copied: boolean
  try {
    // Deprecated, and still the only way without HTTPS - which Muninn at home does not have.
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    copied = document.execCommand('copy')
  } catch {
    copied = false
  }
  field.remove()
  return copied
}
