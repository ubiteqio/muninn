import { Link, Navigate } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageColumn } from '@/components/layout/page-column'
import { PageHeading } from '@/components/layout/page-heading'
import { useAuthStore } from '@/features/auth/auth-store'
import { cn } from '@/lib/utils'

export type AdminSection =
  'report' | 'settings' | 'folders' | 'jobs' | 'ai' | 'users' | 'duplicates'

const SECTIONS = [
  { id: 'settings', to: '/admin/settings' },
  { id: 'folders', to: '/admin/folders' },
  { id: 'jobs', to: '/admin/jobs' },
  { id: 'ai', to: '/admin/ai' },
  { id: 'users', to: '/admin/users' },
  { id: 'duplicates', to: '/admin/duplicates' },
] as const

/**
 * The frame around every admin page: the title, the sections and the guard.
 *
 * The API refuses each of these endpoints to anybody but an admin, so this is not what keeps the
 * area closed - it keeps a user who typed the address from staring at a page of failures.
 */
export function AdminArea({ section, children }: { section: AdminSection; children: ReactNode }) {
  const { t } = useTranslation()
  const isAdmin = useAuthStore((state) => state.user?.role === 'admin')

  if (!isAdmin) return <Navigate to="/home" replace />

  return (
    <AppShell title={t('admin.title')} active="admin">
      <PageColumn className="space-y-5">
        <PageHeading title={t('admin.title')} description={t('admin.description')} />

        <nav aria-label={t('admin.title')} className="-mx-1 flex gap-2 overflow-x-auto px-1">
          {SECTIONS.map((item) => {
            const isActive = item.id === section
            return (
              <Link
                key={item.id}
                to={item.to}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'rounded-lg px-3.5 py-2 text-base font-medium transition',
                  isActive
                    ? 'bg-primary/[0.12] text-primary'
                    : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                )}
              >
                {t(`admin.section.${item.id}`)}
              </Link>
            )
          })}
        </nav>

        {children}
      </PageColumn>
    </AppShell>
  )
}
