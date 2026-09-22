import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => {
    observer.disconnect()
  }
}

function isDark(): boolean {
  return document.documentElement.classList.contains('dark')
}

/** Whether the page is dark right now - for what CSS cannot reach, like a map's own style. */
export function useDark(): boolean {
  return useSyncExternalStore(subscribe, isDark, () => true)
}
