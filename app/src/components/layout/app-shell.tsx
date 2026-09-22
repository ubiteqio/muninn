import { type ReactNode, useState } from 'react'

import { DesktopHeader } from '@/components/layout/desktop-header'
import { MobileHeader } from '@/components/layout/mobile-header'
import { MobileNav } from '@/components/layout/mobile-nav'
import { ScrollContainerProvider } from '@/components/layout/scroll-container'
import { Sidebar } from '@/components/layout/sidebar'
import { DESKTOP_QUERY, useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

interface AppShellProps {
  /** The page name. Shown by the page itself; here it is only the heading for screen readers. */
  title: string
  active: string
  children: ReactNode
  /** The 352 px column on the desktop. Below 1024 px its content follows the main column. */
  aside?: ReactNode
  /** The page fills the column edge to edge and does not scroll, like the map. */
  fill?: boolean
}

/**
 * One shell for every width:
 * - below 768 px the mobile layout with a bottom navigation bar,
 * - from 768 px the sidebar with a single content column,
 * - from 1024 px the sidebar plus the aside as a second column.
 *
 * The layout is chosen, not hidden with CSS: rendering both would put every headline, photo and
 * link into the page twice, which screen readers and the timeline's element lookups would see.
 */
export function AppShell({ title, active, children, aside, fill = false }: AppShellProps) {
  const [scrollContainer, setScrollContainer] = useState<HTMLElement | null>(null)
  const isWide = useMediaQuery(WIDE_QUERY)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)

  return (
    <div className="flex h-full overflow-hidden bg-background">
      {isWide && <Sidebar active={active} />}

      <div className="flex min-w-0 flex-1 flex-col">
        {isWide && <DesktopHeader />}
        {!isWide && <MobileHeader />}

        <ScrollContainerProvider container={scrollContainer}>
          <div className="flex min-h-0 flex-1">
            <main
              ref={setScrollContainer}
              className={
                fill
                  ? 'relative min-h-0 flex-1 overflow-hidden'
                  : isWide
                    ? 'scrollbar-stable min-h-0 flex-1 overflow-y-scroll px-7 pb-10 pt-6'
                    : 'min-h-0 flex-1 overflow-y-auto pb-[110px] pt-5'
              }
            >
              {/* The desktop header shows no title, so the page name lives here for anybody who
                  navigates by headings. Narrow layouts print it through PageHeading instead. */}
              {isWide && <h1 className="sr-only">{title}</h1>}
              {children}
              {/* Between 768 and 1024 px the aside has no column of its own and follows below. */}
              {aside && isWide && !isDesktop && <div className="mt-6">{aside}</div>}
            </main>

            {aside && isDesktop && (
              <aside className="scrollbar-stable min-h-0 w-aside shrink-0 overflow-y-scroll border-l border-hairline/[0.08] bg-secondary/30 px-5 py-6">
                {aside}
              </aside>
            )}
          </div>
        </ScrollContainerProvider>
      </div>

      {!isWide && <MobileNav active={active} />}
    </div>
  )
}
