import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { OwnAvatar } from '@/components/layout/own-avatar'
import { PageColumn } from '@/components/layout/page-column'
import { PageHeading } from '@/components/layout/page-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuthStore } from '@/features/auth/auth-store'
import { AppearanceCard } from '@/features/profile/appearance-card'
import { ChangePasswordCard } from '@/features/profile/change-password-card'
import { NotificationsCard } from '@/features/profile/notifications-card'

/**
 * The own account, and the way out. The full profile screen is not designed yet; this is built
 * from the tokens so that signing out has a home and does not hide behind the avatar.
 */
export function ProfileScreen() {
  const { t } = useTranslation()
  const user = useAuthStore((state) => state.user)
  const signOut = useAuthStore((state) => state.signOut)

  return (
    <AppShell title={t('nav.profile')} active="profile">
      <PageColumn className="space-y-6">
        <PageHeading title={t('nav.profile')} />

        <Card className="flex items-center gap-4 p-5">
          <OwnAvatar name={user?.display_name ?? ''} size={56} />
          <div className="min-w-0">
            <p className="truncate text-md font-semibold text-foreground">{user?.display_name}</p>
            {user?.email && (
              <p className="truncate text-base text-muted-foreground">{user.email}</p>
            )}
            <p className="mt-1 text-xs-plus text-muted-foreground">
              {t(user?.role === 'admin' ? 'profile.roleAdmin' : 'profile.roleUser')}
            </p>
          </div>
        </Card>

        <Button variant="outline" className="w-full justify-start" asChild>
          <Link to="/favorites">
            <Symbol name="star" size={20} />
            {t('walhall.title')}
          </Link>
        </Button>

        {user?.role === 'admin' && (
          <Button variant="outline" className="w-full justify-start" asChild>
            <Link to="/admin">
              <Symbol name="shield_person" size={20} />
              {t('admin.title')}
            </Link>
          </Button>
        )}

        <NotificationsCard />

        <AppearanceCard />

        <ChangePasswordCard />

        <Button variant="outline" className="w-full" onClick={() => void signOut()}>
          <Symbol name="logout" size={20} />
          {t('auth.signOut')}
        </Button>
      </PageColumn>
    </AppShell>
  )
}
