import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { LogoMark } from '@/components/layout/logo'
import { useNavigation } from '@/components/layout/navigation'
import { OwnAvatar } from '@/components/layout/own-avatar'
import { Knotwork } from '@/components/muninn/knotwork'
import { Symbol } from '@/components/muninn/symbol'
import { useAuthStore } from '@/features/auth/auth-store'
import { cn } from '@/lib/utils'

/** The 96 px rail of the desktop layout: logo, wordmark, knotwork, destinations, own avatar. */
export function Sidebar({ active }: { active: string }) {
  const { t } = useTranslation()
  const displayName = useAuthStore((state) => state.user?.display_name ?? '')
  const destinations = useNavigation()

  return (
    <aside className="hidden w-rail shrink-0 flex-col items-center border-r border-hairline/[0.08] bg-card py-5 md:flex">
      <Link to="/home" aria-label={t('header.home')} className="flex flex-col items-center">
        <LogoMark size={48} className="rounded-mark-lg" />
        <span className="mt-2 text-[10.5px] font-semibold tracking-wordmark-rail text-muted-foreground">
          MUNINN
        </span>
      </Link>
      <Knotwork className="mt-3 w-10" />

      <nav aria-label={t('nav.label')} className="mt-4 flex w-full flex-1 flex-col gap-1 px-4">
        {destinations.map((item) => {
          const isActive = item.id === active
          return (
            <Link
              key={item.id}
              to={item.to}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                'flex h-16 flex-col items-center justify-center gap-1 rounded-lg transition',
                isActive
                  ? 'bg-primary/[0.12] text-primary'
                  : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
              )}
            >
              <Symbol name={item.icon} size={24} filled={isActive} />
              <span className={cn('text-2xs', isActive ? 'font-semibold' : 'font-medium')}>
                {t(`nav.${item.id}`)}
              </span>
            </Link>
          )
        })}
      </nav>

      <button type="button" aria-label={t('header.profile')}>
        <OwnAvatar name={displayName} size={40} />
      </button>
    </aside>
  )
}
