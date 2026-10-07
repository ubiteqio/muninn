import type { TFunction } from 'i18next'
import { type ReactNode, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Toggle } from '@/components/muninn/toggle'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { RoleChoice } from '@/features/admin/role-choice'
import {
  type AccountChanges,
  useDeleteUser,
  type User,
  useUpdateUser,
} from '@/features/admin/use-users'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'
import { initialsOf } from '@/features/auth/initials'
import { MIN_PASSWORD_LENGTH, passwordProblem } from '@/features/auth/password-rules'
import { Face } from '@/features/people/face'
import { usePeople } from '@/features/people/use-people'
import { cn } from '@/lib/utils'

export function UserRow({ user, isSelf }: { user: User; isSelf: boolean }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const disabled = user.status === 'disabled'

  return (
    <li className="border-b border-hairline/[0.06] last:border-b-0">
      <button
        type="button"
        onClick={() => {
          setExpanded(!expanded)
        }}
        aria-expanded={expanded}
        className="flex w-full items-center gap-3 p-4 text-left transition hover:bg-secondary/40"
      >
        <span
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#EDE6D6]/[0.18] text-base font-bold text-[#0B0D12]',
            disabled ? 'bg-muted-foreground/40' : 'bg-[#8FA9C9]',
          )}
        >
          {initialsOf(user.display_name)}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-md font-semibold text-foreground">
              {user.display_name}
            </span>
            {user.role === 'admin' && (
              <Symbol name="shield_person" size={16} className="shrink-0 text-primary" />
            )}
          </span>
          <span className="block truncate text-xs-plus text-muted-foreground">
            {user.username}
            {disabled && ` · ${t('admin.users.status.disabled')}`}
            {user.must_change_password && ` · ${t('admin.users.status.startingPassword')}`}
            {user.person && ` · ${t('admin.users.person.short', { name: user.person.name })}`}
          </span>
        </span>

        <Symbol
          name="expand_more"
          size={20}
          className={cn('shrink-0 text-muted-foreground transition', expanded && 'rotate-180')}
        />
      </button>

      {expanded && (
        <div className="border-t border-hairline/[0.06] bg-background/40 p-4">
          <AccountForm user={user} isSelf={isSelf} />
        </div>
      )}
    </li>
  )
}

/**
 * Everything about an account in one form - name, username, address, role, the person on the
 * photos, locked or not, a new password - saved together. Only what changed is sent; an emptied
 * address is taken away, an empty password field keeps the password.
 */
function AccountForm({ user, isSelf }: { user: User; isSelf: boolean }) {
  const { t } = useTranslation()
  const updateUser = useUpdateUser()
  const deleteUser = useDeleteUser()

  const [displayName, setDisplayName] = useState(user.display_name)
  const [username, setUsername] = useState(user.username)
  const [email, setEmail] = useState(user.email ?? '')
  const [role, setRole] = useState(user.role)
  const [personId, setPersonId] = useState<string | null>(user.person?.id ?? null)
  const [locked, setLocked] = useState(user.status === 'disabled')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const changes: AccountChanges = {
    ...(displayName.trim() !== user.display_name ? { display_name: displayName.trim() } : {}),
    ...(username.trim() !== user.username ? { username: username.trim() } : {}),
    ...(email.trim() !== (user.email ?? '') ? { email: email.trim() } : {}),
    ...(role !== user.role ? { role } : {}),
    ...(locked !== (user.status === 'disabled')
      ? { status: locked ? ('disabled' as const) : ('active' as const) }
      : {}),
    ...(password ? { password } : {}),
    ...(personId !== (user.person?.id ?? null) ? { person_id: personId } : {}),
  }
  const changed = Object.keys(changes).length > 0
  const busy = updateUser.isPending || deleteUser.isPending

  async function save() {
    setError(null)
    setSaved(false)
    const weak = password ? passwordProblem(password) : null
    if (weak) {
      setError(t(`auth.error.${weak}`, { count: MIN_PASSWORD_LENGTH }))
      return
    }
    try {
      await updateUser.mutateAsync({ id: user.id, ...changes })
      setPassword('')
      setSaved(true)
    } catch (failure) {
      setError(messageFor(failure, t))
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (changed) void save()
      }}
      // Two columns from the tablet up: across the card's width, single fields grew too long.
      className="space-y-4"
      noValidate
    >
      <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
        <Field
          label={t('admin.users.create.displayName')}
          value={displayName}
          onChange={(event) => {
            setDisplayName(event.target.value)
          }}
        />
        <Field
          label={t('auth.username')}
          value={username}
          onChange={(event) => {
            setUsername(event.target.value)
          }}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
        />
        <Field
          label={t('admin.users.email')}
          hint={t('admin.users.emailHint')}
          type="email"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value)
          }}
        />
        <Field
          label={t('admin.users.password.label')}
          hint={t('admin.users.password.hint', { count: MIN_PASSWORD_LENGTH })}
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value)
            setSaved(false)
          }}
        />
        <RoleChoice value={role} onChange={setRole} disabled={busy} />
        <PersonChoice user={user} value={personId} onChange={setPersonId} disabled={busy} />
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-hairline/10 bg-card px-3 py-2.5">
        <div>
          <p className="text-md font-medium text-foreground">{t('admin.users.locked.label')}</p>
          <p className="text-xs-plus text-muted-foreground">
            {t(isSelf ? 'admin.users.locked.self' : 'admin.users.locked.hint')}
          </p>
        </div>
        <Toggle
          label={t('admin.users.locked.label')}
          checked={locked}
          onChange={setLocked}
          disabled={isSelf || busy}
        />
      </div>

      <FormError message={error} />

      <div className="flex flex-wrap items-center gap-2 border-t border-hairline/[0.06] pt-4">
        <Button type="submit" disabled={!changed || busy}>
          <Symbol name="check_circle" size={20} />
          {t('admin.users.action.save')}
        </Button>
        {!isSelf && (
          <ConfirmDialog
            trigger={
              <Button type="button" variant="outline" disabled={busy}>
                <Symbol name="delete" size={20} />
                {t('admin.users.action.delete')}
              </Button>
            }
            title={t('admin.users.delete.title', { name: user.display_name })}
            description={t('admin.users.delete.description')}
            confirmLabel={t('admin.users.delete.confirm')}
            cancelLabel={t('admin.folders.action.cancel')}
            closeLabel={t('common.close')}
            destructive
            pending={deleteUser.isPending}
            onConfirm={async () => {
              setError(null)
              try {
                await deleteUser.mutateAsync(user.id)
              } catch (failure) {
                setError(messageFor(failure, t))
              }
            }}
          />
        )}
        {saved && !changed && (
          <span role="status" className="text-xs-plus text-muted-foreground">
            {t('admin.users.saved')}
          </span>
        )}
      </div>

      {isSelf && <p className="text-xs-plus text-muted-foreground">{t('admin.users.selfHint')}</p>}
    </form>
  )
}

/**
 * Which person on the photos signs in with this account: they hear of comments and reactions on
 * photos of them. Saved with the rest of the form.
 */
function PersonChoice({
  user,
  value,
  onChange,
  disabled,
}: {
  user: User
  value: string | null
  onChange: (personId: string | null) => void
  disabled: boolean
}) {
  const { t } = useTranslation()
  const labelId = useId()
  const hintId = useId()
  const [open, setOpen] = useState(false)
  const people = usePeople()
  const current = value
  // A hidden person is not among the shown ones; the one this account has stays choosable.
  const shown: Choosable[] = people.data?.persons ?? []
  const persons: Choosable[] = [
    ...shown,
    ...(user.person && !shown.some((person) => person.id === user.person?.id) ? [user.person] : []),
  ].sort((a, b) => a.name.localeCompare(b.name))
  const chosen = persons.find((person) => person.id === current)

  function choose(personId: string | null) {
    setOpen(false)
    onChange(personId)
  }

  return (
    <div className="space-y-1.5">
      <p id={labelId} className="text-sm font-medium text-muted-foreground">
        {t('admin.users.person.label')}
      </p>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-haspopup="listbox"
            aria-labelledby={labelId}
            aria-describedby={hintId}
            disabled={disabled || people.isPending}
            className="flex h-11 w-full items-center gap-2.5 rounded-lg border border-hairline/10 bg-card px-3 text-left text-md text-foreground transition hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-60"
          >
            {chosen ? (
              <Face src={chosen.cover?.crop} size={26} />
            ) : (
              <Symbol name="person" size={20} className="text-muted-foreground" />
            )}
            <span className={cn('flex-1 truncate', !chosen && 'text-muted-foreground')}>
              {chosen?.name ?? t('admin.users.person.none')}
            </span>
            <Symbol name="expand_more" size={20} className="text-muted-foreground" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-1.5">
          <ul role="listbox" aria-labelledby={labelId} className="max-h-72 overflow-y-auto">
            <PersonOption
              selected={current === null}
              onChoose={() => {
                choose(null)
              }}
            >
              <Symbol name="person" size={20} className="mx-[3px] text-muted-foreground" />
              <span className="text-muted-foreground">{t('admin.users.person.none')}</span>
            </PersonOption>
            {persons.map((person) => (
              <PersonOption
                key={person.id}
                selected={person.id === current}
                onChoose={() => {
                  choose(person.id)
                }}
              >
                <Face src={person.cover?.crop} size={26} />
                <span className="truncate">{person.name}</span>
              </PersonOption>
            ))}
          </ul>
        </PopoverContent>
      </Popover>
      <p id={hintId} className="text-xs-plus text-muted-foreground">
        {people.isSuccess && persons.length === 0
          ? t('admin.users.person.empty')
          : t('admin.users.person.hint')}
      </p>
    </div>
  )
}

/** A person to choose: from the people list with a face, or the hidden one an account has. */
type Choosable = { id: string; name: string; cover?: { crop: string } | null }

function PersonOption({
  selected,
  onChoose,
  children,
}: {
  selected: boolean
  onChoose: () => void
  children: ReactNode
}) {
  return (
    <li role="option" aria-selected={selected}>
      <button
        type="button"
        onClick={onChoose}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-md text-foreground transition hover:bg-secondary/60 focus-visible:bg-secondary/60 focus-visible:outline-none',
          selected && 'bg-secondary/40',
        )}
      >
        {children}
        {selected && (
          <Symbol name="check_circle" size={18} filled className="ml-auto shrink-0 text-primary" />
        )}
      </button>
    </li>
  )
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  if (failure.is('last-admin')) return t('admin.users.error.lastAdmin')
  if (failure.is('name-already-used')) return t('admin.users.error.nameOrEmailTaken')
  if (failure.is('own-account')) return t('admin.users.error.ownAccount')
  if (failure.status === 422) return t('admin.users.error.invalidUsername')
  return failure.problem.detail ?? t('auth.error.unexpected')
}
