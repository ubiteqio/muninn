import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError } from '@/api/problem'
import { Button } from '@/components/ui/button'
import { AuthLayout } from '@/features/auth/auth-layout'
import { useAuthStore } from '@/features/auth/auth-store'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'
import { MIN_PASSWORD_LENGTH, passwordProblem } from '@/features/auth/password-rules'

/**
 * Shown while the starting password an admin handed out is still in place. Until it is replaced
 * the API refuses everything except the own account, so there is nowhere else to go.
 */
export function PasswordScreen() {
  const { t } = useTranslation()
  const setPassword = useAuthStore((state) => state.setPassword)
  const signOut = useAuthStore((state) => state.signOut)

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit() {
    setError(null)

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
    } catch (failure) {
      setError(messageFor(failure, t))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout title={t('auth.setPassword.title')} description={t('auth.setPassword.description')}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
        className="mt-5 space-y-4"
        noValidate
      >
        <Field
          label={t('auth.setPassword.current')}
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

        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? t('auth.setPassword.pending') : t('auth.setPassword.submit')}
        </Button>
      </form>

      <Button
        variant="ghost"
        className="mt-3 w-full"
        onClick={() => void signOut()}
        disabled={pending}
      >
        {t('auth.signOut')}
      </Button>
    </AuthLayout>
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
