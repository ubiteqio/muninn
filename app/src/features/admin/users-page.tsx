import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { CreateUserDialog } from '@/features/admin/create-user-dialog'
import { useUsers } from '@/features/admin/use-users'
import { UserRow } from '@/features/admin/user-row'
import { useAuthStore } from '@/features/auth/auth-store'

/**
 * The admin area for accounts: who exists, who may do what, and the way back in for somebody who
 * forgot their password. Admins only; the API enforces the same and this screen is not reachable
 * for anybody else.
 */
export function AdminUsersPage() {
  const { t } = useTranslation()
  const self = useAuthStore((state) => state.user)
  const { data, isPending, isError, hasNextPage, fetchNextPage, isFetchingNextPage } = useUsers()

  const users = data?.pages.flatMap((page) => page.items) ?? []

  return (
    <AdminArea section="users">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{t('admin.users.title')}</h2>
          <p className="mt-1.5 text-base text-muted-foreground">{t('admin.users.description')}</p>
        </div>
        <CreateUserDialog />
      </div>

      {isPending && <p className="text-base text-muted-foreground">{t('admin.users.loading')}</p>}
      {isError && <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>}

      {users.length > 0 && (
        <Card className="overflow-hidden">
          <ul>
            {users.map((user) => (
              <UserRow key={user.id} user={user} isSelf={user.id === self?.id} />
            ))}
          </ul>
        </Card>
      )}

      {hasNextPage && (
        <Button
          variant="outline"
          className="w-full"
          onClick={() => void fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {t(isFetchingNextPage ? 'admin.users.loading' : 'admin.users.loadMore')}
        </Button>
      )}
    </AdminArea>
  )
}
