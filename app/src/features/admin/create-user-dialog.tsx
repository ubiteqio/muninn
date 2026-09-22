import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { RoleChoice } from '@/features/admin/role-choice'
import { StartingPassword } from '@/features/admin/starting-password'
import { useCreateUser, type UserRole } from '@/features/admin/use-users'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'

export function CreateUserDialog() {
  const { t } = useTranslation()
  const createUser = useCreateUser()

  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ name: string; password: string } | null>(null)

  function reset() {
    setUsername('')
    setDisplayName('')
    setRole('user')
    setError(null)
    setCreated(null)
  }

  async function submit() {
    setError(null)
    try {
      const result = await createUser.mutateAsync({
        username: username.trim(),
        display_name: displayName.trim(),
        role,
      })
      setCreated({ name: result.user.display_name, password: result.starting_password })
    } catch (failure) {
      setError(messageFor(failure, t))
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Symbol name="person_add" size={20} />
          {t('admin.users.create.action')}
        </Button>
      </DialogTrigger>

      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('admin.users.create.title')}</DialogTitle>
        <DialogDescription>{t('admin.users.create.description')}</DialogDescription>

        {created ? (
          <div className="mt-4 space-y-4">
            <StartingPassword password={created.password} name={created.name} />
            <div className="flex gap-2">
              <Button variant="outline" onClick={reset}>
                {t('admin.users.create.another')}
              </Button>
              <Button
                onClick={() => {
                  setOpen(false)
                  reset()
                }}
              >
                {t('common.done')}
              </Button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void submit()
            }}
            className="mt-4 space-y-4"
            noValidate
          >
            <Field
              label={t('auth.username')}
              hint={t('admin.users.create.usernameHint')}
              value={username}
              onChange={(event) => {
                setUsername(event.target.value)
              }}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              required
            />
            <Field
              label={t('admin.users.create.displayName')}
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value)
              }}
              required
            />
            <RoleChoice value={role} onChange={setRole} />

            <FormError message={error} />

            <Button type="submit" className="w-full" disabled={createUser.isPending}>
              {createUser.isPending
                ? t('admin.users.create.pending')
                : t('admin.users.create.submit')}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  if (failure.is('name-already-used')) return t('admin.users.error.nameTaken')
  if (failure.is('validation-failed')) return t('admin.users.error.invalidUsername')
  return failure.problem.detail ?? t('auth.error.unexpected')
}
