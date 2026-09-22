import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { LogoMark, Wordmark } from '@/components/layout/logo'
import { OwnAvatar } from '@/components/layout/own-avatar'
import { Symbol } from '@/components/muninn/symbol'
import { useAuthStore } from '@/features/auth/auth-store'
import { NotificationBell } from '@/features/notify/notification-bell'

/**
 * Sticky bar below the system status bar: logo, wordmark, notification bell and the own avatar.
 * The glass effect is part of the design; photos scroll underneath it.
 */
export function MobileHeader() {
  const { t } = useTranslation()
  const displayName = useAuthStore((state) => state.user?.display_name ?? '')
  const isAdmin = useAuthStore((state) => state.user?.role === 'admin')

  const avatar = <OwnAvatar name={displayName} />

  return (
    // The status bar's room (notch, clock) comes on top of the bar's own height instead of out
    // of it; and at the sides at least 20 px, more where the device rounds its corners.
    <header className="sticky top-0 z-20 box-content flex h-[60px] items-center justify-between border-b border-hairline/[0.08] bg-background/[0.86] pl-[max(env(safe-area-inset-left),20px)] pr-[max(env(safe-area-inset-right),16px)] pt-safe-top backdrop-blur-bar">
      {/* The mark leads home, as a logo does everywhere. */}
      <Link to="/home" aria-label={t('header.home')} className="flex items-center gap-2.5">
        <LogoMark />
        <Wordmark />
      </Link>

      <div className="flex items-center gap-1">
        {/* The search is up here on the phone: the bottom bar gives its place to the Überblick. */}
        <Link
          to="/search"
          aria-label={t('nav.search')}
          title={t('nav.search')}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-secondary hover:text-foreground data-[status=active]:text-primary"
        >
          <Symbol name="search" size={24} />
        </Link>
        <NotificationBell />

        {/* The bottom bar has no room for a sixth destination, so for an admin the own avatar is
            the way into the admin area. */}
        {isAdmin ? (
          <Link to="/admin" aria-label={t('header.admin')}>
            {avatar}
          </Link>
        ) : (
          <button type="button" aria-label={t('header.profile')}>
            {avatar}
          </button>
        )}
      </div>
    </header>
  )
}
