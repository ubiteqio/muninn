import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { MOBILE_MORE, MOBILE_NAVIGATION } from '@/components/layout/navigation'
import { Symbol } from '@/components/muninn/symbol'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

const TARGET = 'flex h-[56px] w-full items-center justify-center'

/** Without a label under it, an icon may take a little more room. */
const ICON = 28

/**
 * Five equal targets, fixed to the bottom edge: Alben, Karte, Home, Personen, and "Mehr",
 * which opens Überblick and Profil above the bar. Icons only - each carries its name for screen
 * readers - and the page that is open shows as the amber, filled one. The search sits in the header beside the
 * bell. Below them the system's own home indicator gets the room it asks for (safe area); the
 * app draws none of its own - it read as a stray line.
 *
 * The admin area is not among them: a sixth target would cramp the row for everybody to serve
 * one person. On the phone it hangs on the own avatar in the header instead.
 */
export function MobileNav({ active }: { active: string }) {
  const { t } = useTranslation()
  // "Mehr" stands for the page behind it while one of them is open.
  const moreActive = MOBILE_MORE.some((item) => item.id === active)

  return (
    <nav
      aria-label={t('nav.label')}
      // Rounded at the top and lifted by a soft shadow: a sheet the page slides under, rather than
      // a hard line across the screen.
      className="fixed inset-x-0 bottom-0 z-20 rounded-t-[22px] border-t border-hairline/[0.09] bg-card/[0.96] pb-[max(env(safe-area-inset-bottom),6px)] shadow-[0_-10px_30px_-14px_rgba(0,0,0,0.55)] backdrop-blur-nav md:hidden"
    >
      <ul className="flex">
        {MOBILE_NAVIGATION.map((item) => {
          const isActive = item.id === active
          if (item.id === 'home') {
            return (
              <li key={item.id} className="relative flex-1">
                <HomeTarget to={item.to} label={t(`nav.${item.id}`)} active={isActive} />
              </li>
            )
          }
          return (
            <li key={item.id} className="flex-1">
              <Link
                to={item.to}
                aria-label={t(`nav.${item.id}`)}
                aria-current={isActive ? 'page' : undefined}
                className={cn(TARGET, isActive ? 'text-primary' : 'text-muted-foreground')}
              >
                <Symbol name={item.icon} size={ICON} filled={isActive} />
              </Link>
            </li>
          )
        })}
        <li className="flex-1">
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label={t('nav.more')}
              className={cn(TARGET, moreActive ? 'text-primary' : 'text-muted-foreground')}
            >
              <Symbol name="more_horiz" size={ICON} filled={moreActive} />
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="end" className="mr-2">
              {MOBILE_MORE.map((item) => {
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
        </li>
      </ul>
    </nav>
  )
}

/**
 * Home, raised out of the bar: a disc in the bar's own colour rises above its top edge - only its
 * upper arc carries the edge line, so it reads as a bump of the bar, not a button laid on top -
 * and holds a round button, amber while Home is open.
 */
function HomeTarget({ to, label, active }: { to: '/home'; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'group flex h-[56px] w-full',
        active ? 'text-primary' : 'text-muted-foreground',
      )}
    >
      <span
        aria-hidden="true"
        className="absolute -top-[14px] left-1/2 flex h-[66px] w-[66px] -translate-x-1/2 items-center justify-center rounded-full border-t border-hairline/[0.09] bg-card/[0.96] backdrop-blur-nav"
      >
        <span
          className={cn(
            'flex h-[52px] w-[52px] items-center justify-center rounded-full shadow-[0_6px_16px_-6px_rgba(0,0,0,0.45)] transition-colors',
            active
              ? 'bg-primary text-primary-foreground'
              : 'bg-secondary text-foreground group-active:bg-secondary/70',
          )}
        >
          <Symbol name="home" size={ICON} filled={active} />
        </span>
      </span>
    </Link>
  )
}
