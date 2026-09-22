import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiServerChanged } from '@/api/client'
import { isApiError } from '@/api/problem'
import { Button } from '@/components/ui/button'
import { AuthLayout } from '@/features/auth/auth-layout'
import { useAuthStore } from '@/features/auth/auth-store'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'
import { isNative, rememberServer, serverOrigin } from '@/platform/server'

export function LoginScreen() {
  const { t } = useTranslation()
  const signIn = useAuthStore((state) => state.signIn)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  // On a phone the app is not served by Muninn, so it has to be told where Muninn is. The
  // address is remembered on the device and only asked for again if it stops working.
  const [server, setServer] = useState(serverOrigin())
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit() {
    setError(null)
    setPending(true)

    try {
      if (isNative()) {
        rememberServer(server)
        apiServerChanged()
      }
      await signIn(username, password)
    } catch (failure) {
      setError(messageFor(failure, t))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout title={t('auth.login.title')} description={t('auth.login.description')}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
        className="mt-5 space-y-4"
        noValidate
      >
        {isNative() && (
          <Field
            label={t('auth.server')}
            hint={t('auth.serverHint')}
            type="url"
            name="server"
            inputMode="url"
            value={server}
            onChange={(event) => {
              setServer(event.target.value)
            }}
            placeholder="muninn.zuhause.example"
            autoComplete="url"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
          />
        )}
        <Field
          label={t('auth.username')}
          type="text"
          name="username"
          value={username}
          onChange={(event) => {
            setUsername(event.target.value)
          }}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          required
        />
        <Field
          label={t('auth.password')}
          type="password"
          name="password"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value)
          }}
          autoComplete="current-password"
          required
        />

        <FormError message={error} />

        <Button type="submit" className="w-full" disabled={pending}>
          {pending ? t('auth.login.pending') : t('auth.login.submit')}
        </Button>
      </form>
    </AuthLayout>
  )
}

/** Turns a Problem Details type into something a person can act on. */
function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) {
    return isNative() ? t('auth.error.unreachableServer') : t('auth.error.unreachable')
  }

  if (failure.is('invalid-credentials')) return t('auth.error.invalidCredentials')
  if (failure.is('account-disabled')) return t('auth.error.accountDisabled')
  if (failure.is('too-many-login-attempts')) {
    const seconds = failure.retryAfterSeconds ?? 0
    return t('auth.error.throttled', { count: Math.max(1, Math.ceil(seconds / 60)) })
  }
  if (failure.is('validation-failed')) return t('auth.error.invalidCredentials')

  return failure.problem.detail ?? t('auth.error.unexpected')
}
