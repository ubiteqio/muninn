import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuthStore } from '@/features/auth/auth-store'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'
import { MIN_PASSWORD_LENGTH, passwordProblem } from '@/features/auth/password-rules'

/**
 * Changing the own password from the profile. The server signs every other device out and keeps
 * this one, so there is nothing to do here afterwards but say so.
 */
export function ChangePasswordCard() {
  const { t } = useTranslation()
  const setPassword = useAuthStore((state) => state.setPassword)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [pending, setPending] = useState(false)

  async function submit() {
    setError(null)
    setDone(false)

    const problem = passwordProblem(next)
    if (problem !== null) {
      setError(t(`auth.error.${problem}`, { count: MIN_PASSWORD_LENGTH }))
      return
    }
    if (next !== repeat) {
      setError(t('auth.error.mismatch'))
      return
    }

    setPending(true)
    try {
      await setPassword(current, next)
      setCurrent('')
      setNext('')
      setRepeat('')
      setDone(true)
    } catch (failure) {
      setError(messageFor(failure, t))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-foreground">{t('profile.password.title')}</h2>
      <p className="mt-1.5 text-base text-muted-foreground">{t('profile.password.description')}</p>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
        className="mt-4 space-y-4"
        noValidate
      >
        <Field
          label={t('profile.password.current')}
          type="password"
          value={current}
          onChange={(event) => {
            setCurrent(event.target.value)
          }}
          autoComplete="current-password"
          required
        />
        <Field
          label={t('auth.setPassword.new')}
          hint={t('auth.setPassword.hint', { count: MIN_PASSWORD_LENGTH })}
          type="password"
          value={next}
          onChange={(event) => {
            setNext(event.target.value)
          }}
          autoComplete="new-password"
          required
        />
        <Field
          label={t('auth.setPassword.repeat')}
          type="password"
          value={repeat}
          onChange={(event) => {
            setRepeat(event.target.value)
          }}
          autoComplete="new-password"
          required
        />

        <FormError message={error} />

        {done && (
          <p
            role="status"
            className="flex items-start gap-2 rounded-md border border-primary/40 bg-primary/[0.12] px-3 py-2 text-base text-foreground"
          >
            <Symbol name="check_circle" size={18} filled className="mt-px shrink-0 text-primary" />
            {t('profile.password.done')}
          </p>
        )}

        <Button type="submit" disabled={pending}>
          {pending ? t('auth.setPassword.pending') : t('profile.password.submit')}
        </Button>
      </form>
    </Card>
  )
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  if (failure.is('invalid-credentials')) return t('auth.error.wrongCurrentPassword')
  if (failure.is('validation-failed')) {
    return t('auth.error.weakPassword', { count: MIN_PASSWORD_LENGTH })
  }
  return failure.problem.detail ?? t('auth.error.unexpected')
}
