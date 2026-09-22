import { useTranslation } from 'react-i18next'

import type { UserRole } from '@/features/admin/use-users'
import { cn } from '@/lib/utils'

const ROLES: UserRole[] = ['user', 'admin']

/**
 * Two roles, so two buttons rather than a dropdown: the choice and its consequence are both
 * visible without opening anything.
 */
export function RoleChoice({
  value,
  onChange,
  disabled = false,
}: {
  value: UserRole
  onChange: (role: UserRole) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()

  return (
    <fieldset disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium text-muted-foreground">
        {t('admin.users.role.label')}
      </legend>
      <div className="flex gap-2" role="radiogroup" aria-label={t('admin.users.role.label')}>
        {ROLES.map((role) => (
          <button
            key={role}
            type="button"
            role="radio"
            aria-checked={value === role}
            onClick={() => {
              onChange(role)
            }}
            className={cn(
              'h-11 flex-1 rounded-lg border text-md transition',
              value === role
                ? 'border-primary bg-primary/[0.14] font-semibold text-primary'
                : 'border-hairline/10 text-muted-foreground hover:bg-secondary hover:text-foreground',
              'disabled:opacity-50',
            )}
          >
            {t(`admin.users.role.${role}`)}
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-xs-plus text-muted-foreground">
        {t(`admin.users.role.${value}Hint`)}
      </p>
    </fieldset>
  )
}
