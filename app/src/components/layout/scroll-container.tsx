import { createContext, type ReactNode, use } from 'react'

/**
 * The element that actually scrolls the current screen: the page area on mobile, the left column
 * on the desktop. The shell owns it and hands it down, so a section deep in the tree - the
 * timeline scrubber - can follow and drive the scroll position without reaching into the DOM.
 */
const ScrollContainerContext = createContext<HTMLElement | null>(null)

export function ScrollContainerProvider({
  container,
  children,
}: {
  container: HTMLElement | null
  children: ReactNode
}) {
  return <ScrollContainerContext value={container}>{children}</ScrollContainerContext>
}

export function useScrollContainer(): HTMLElement | null {
  return use(ScrollContainerContext)
}
