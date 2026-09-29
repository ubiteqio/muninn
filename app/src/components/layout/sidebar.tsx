import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { AlbumWays } from '@/components/layout/album-ways'
import { LogoMark } from '@/components/layout/logo'
import { MOBILE_NAVIGATION, moreOf, useNavigation } from '@/components/layout/navigation'
import { OwnAvatar } from '@/components/layout/own-avatar'
import { Knotwork } from '@/components/muninn/knotwork'
import { Symbol } from '@/components/muninn/symbol'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/features/auth/auth-store'
import { SHORT_QUERY, useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'

/** The 96 px rail of the desktop layout: logo, wordmark, knotwork, destinations, own avatar. */
export function Sidebar({ active }: { active: string }) {
  const { t } = useTranslation()
  const displayName = useAuthStore((state) => state.user?.display_name ?? '')
  const destinations = useNavigation()
  // A phone held sideways has 390 px of height for eight destinations, a mark and an avatar.
  // They do not fit at their own size, and a rail one has to scroll is not a rail: it draws
  // itself smaller instead, and the names step aside for the symbols that carry them.
  const isShort = useMediaQuery(SHORT_QUERY)
  const shown = isShort ? MOBILE_NAVIGATION : destinations
  const more = isShort ? moreOf(destinations) : []
  const moreActive = more.some((item) => item.id === active)

  return (
    <aside
      className={cn(
        'hidden w-rail shrink-0 flex-col items-center overflow-hidden border-r border-hairline/[0.08] bg-card md:flex',
        isShort ? 'py-2' : 'py-5',
      )}
    >
      <Link to="/home" aria-label={t('header.home')} className="flex flex-col items-center">
        <LogoMark size={isShort ? 30 : 48} className="rounded-mark-lg" />
        {!isShort && (
          <span className="mt-2 text-[10.5px] font-semibold tracking-wordmark-rail text-muted-foreground">
            MUNINN
          </span>
        )}
      </Link>
      {!isShort && <Knotwork className="mt-3 w-10" />}

      {/* A phone held sideways is 390 px tall with a browser bar in it, and eight entries do
        not fit. They scroll, while the mark above and the avatar below stay where they are -
        the two that lead home and to oneself are the two one reaches for blindly. */}
      <nav
        aria-label={t('nav.label')}
        className={cn(
          'no-scrollbar flex min-h-0 w-full flex-1 flex-col overflow-y-auto',
          isShort ? 'mt-1 justify-evenly gap-0 px-2' : 'mt-4 gap-1 px-4',
        )}
      >
        {shown.map((item) => {
          const isActive = item.id === active
          const seat = cn(
            'flex w-full shrink-0 flex-col items-center justify-center rounded-lg transition',
            isShort ? 'h-9 gap-0' : 'h-16 gap-1',
            isActive
              ? 'bg-primary/[0.12] text-primary'
              : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
          )

          // "Alben" is two places: the folders, and the Smarts. It opens them beside the rail.
          if (item.id === 'albums') {
            return (
              <AlbumWays
                key={item.id}
                trigger={
                  <button type="button" className={seat}>
                    <Symbol name={item.icon} size={isShort ? 20 : 24} filled={isActive} />
                    <span
                      className={cn(
                        isActive ? 'font-semibold' : 'font-medium',
                        isShort ? 'sr-only' : 'text-2xs',
                      )}
                    >
                      {t(`nav.${item.id}`)}
                    </span>
                  </button>
                }
              />
            )
          }

          return (
            <Link
              key={item.id}
              to={item.to}
              aria-current={isActive ? 'page' : undefined}
              className={seat}
            >
              <Symbol name={item.icon} size={isShort ? 20 : 24} filled={isActive} />
              {/* The name is still read out where it cannot be read: a rail of symbols is
                only usable because each one is still called something. */}
              <span
                className={cn(
                  isActive ? 'font-semibold' : 'font-medium',
                  isShort ? 'sr-only' : 'text-2xs',
                )}
              >
                {t(`nav.${item.id}`)}
              </span>
            </Link>
          )
        })}
        {more.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label={t('nav.more')}
              className={cn(
                'flex h-9 shrink-0 items-center justify-center rounded-lg transition',
                moreActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Symbol name="more_horiz" size={20} filled={moreActive} />
            </DropdownMenuTrigger>
            {/* Out to the side: there is nothing above or below it on a screen this short. */}
            <DropdownMenuContent side="right" align="end">
              {more.map((item) => {
                const isActive = item.id === active
                return (
                  <DropdownMenuItem key={item.id} asChild>
                    <Link
                      to={item.to}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(isActive && 'text-primary')}
                    >
                      <Symbol name={item.icon} size={22} filled={isActive} />
                      {t(`nav.${item.id}`)}
                    </Link>
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </nav>

      <button type="button" aria-label={t('header.profile')}>
        <OwnAvatar name={displayName} size={isShort ? 30 : 40} />
      </button>
    </aside>
  )
}
