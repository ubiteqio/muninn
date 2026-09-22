import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, unwrap } from '@/api/client'
import { isApiError } from '@/api/problem'
import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Toggle } from '@/components/muninn/toggle'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { IgnoredNames } from '@/features/admin/ignored-names'
import {
  DERIVATIVE_SETTINGS,
  LIMITS,
  type NumericSetting,
  settingsProblem,
  SYNC_SETTINGS,
} from '@/features/admin/settings-rules'
import { type AppSettings, useSaveSettings, useSettings } from '@/features/admin/use-settings'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'

/** The settings of the installation. Admins only; the area around it turns everybody else away. */
export function AdminSettingsPage() {
  const { t } = useTranslation()
  const { data, isPending, isError } = useSettings()

  return (
    <AdminArea section="settings">
      {isPending && (
        <p className="text-base text-muted-foreground">{t('admin.settings.loading')}</p>
      )}
      {isError && <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>}
      {data && <SettingsForm settings={data} />}
    </AdminArea>
  )
}

type Draft = Record<NumericSetting, string>

function SettingsForm({ settings }: { settings: AppSettings }) {
  const [faces, setFaces] = useState(settings.faces_enabled)
  const { t } = useTranslation()
  const save = useSaveSettings()

  const [numbers, setNumbers] = useState<Draft>(() => draftOf(settings))
  const [ignored, setIgnored] = useState<string[]>(settings.ignored_names)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  function field(setting: NumericSetting) {
    return (
      <Field
        key={setting}
        label={t(`admin.settings.field.${setting}.label`)}
        hint={t(`admin.settings.field.${setting}.hint`, LIMITS[setting])}
        type="number"
        inputMode="numeric"
        min={LIMITS[setting].min}
        max={LIMITS[setting].max}
        value={numbers[setting]}
        onChange={(event) => {
          setDone(false)
          setNumbers({ ...numbers, [setting]: event.target.value })
        }}
      />
    )
  }

  async function submit() {
    setError(null)
    setDone(false)

    const values = Object.fromEntries(
      Object.keys(LIMITS).map((setting) => [setting, Number(numbers[setting as NumericSetting])]),
    ) as Record<NumericSetting, number>

    const problem = settingsProblem(values)
    if (problem === 'previewTooSmall') {
      setError(t('admin.settings.error.previewTooSmall'))
      return
    }
    if (problem) {
      setError(
        t('admin.settings.error.outOfBounds', {
          field: t(`admin.settings.field.${problem.setting}.label`),
          ...problem.params,
        }),
      )
      return
    }

    try {
      await save.mutateAsync({
        ...values,
        ignored_names: ignored,
        // Not on the page yet: the agent on the NAS belongs to milestone 7.
        nas_agent_enabled: settings.nas_agent_enabled,
        faces_enabled: faces,
      })
      setDone(true)
    } catch (failure) {
      setError(messageFor(failure, t))
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
      className="space-y-5"
      noValidate
    >
      <Card className="p-5">
        <h2 className="text-lg font-semibold text-foreground">
          {t('admin.settings.derivatives.title')}
        </h2>
        <p className="mt-1.5 text-base text-muted-foreground">
          {t('admin.settings.derivatives.description')}
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">{DERIVATIVE_SETTINGS.map(field)}</div>
      </Card>

      <Card className="p-5">
        <h2 className="text-lg font-semibold text-foreground">{t('admin.settings.sync.title')}</h2>
        <p className="mt-1.5 text-base text-muted-foreground">
          {t('admin.settings.sync.description')}
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">{SYNC_SETTINGS.map(field)}</div>
      </Card>

      <Card className="p-5">
        <h2 className="text-lg font-semibold text-foreground">
          {t('admin.settings.ignored.title')}
        </h2>
        <p className="mt-1.5 text-base text-muted-foreground">
          {t('admin.settings.ignored.description')}
        </p>

        <IgnoredNames
          names={ignored}
          onChange={(names) => {
            setDone(false)
            setIgnored(names)
          }}
          onInvalid={() => {
            setError(t('admin.settings.error.invalidName'))
          }}
        />
      </Card>

      <Card className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {t('admin.settings.faces.title')}
            </h2>
            <p className="mt-1.5 text-base text-muted-foreground">
              {t('admin.settings.faces.description')}
            </p>
          </div>
          <Toggle
            checked={faces}
            label={t('admin.settings.faces.title')}
            onChange={(on) => {
              setDone(false)
              setFaces(on)
            }}
          />
        </div>
        <ForgetFaces />
      </Card>

      <FormError message={error} />

      {done && (
        <p
          role="status"
          className="flex items-start gap-2 rounded-md border border-primary/40 bg-primary/[0.12] px-3 py-2 text-base text-foreground"
        >
          <Symbol name="check_circle" size={18} filled className="mt-px shrink-0 text-primary" />
          {t('admin.settings.saved')}
        </p>
      )}

      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? t('admin.settings.saving') : t('admin.settings.save')}
      </Button>
    </form>
  )
}

/**
 * Faces are biometric data: every one of them, their vectors and pictures and the names given,
 * gone at once. Switched on again, faces are found anew - the names are not coming back.
 */
function ForgetFaces() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [result, setResult] = useState<{ faces: number; persons: number } | null>(null)
  const forget = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/v1/admin/faces')),
    onSuccess: async (counts) => {
      setResult(counts)
      await queryClient.invalidateQueries({ queryKey: ['people'] })
    },
  })

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-hairline/10 pt-4">
      <ConfirmDialog
        trigger={
          <Button type="button" variant="outline">
            {t('admin.settings.faces.forget')}
          </Button>
        }
        title={t('admin.settings.faces.forgetTitle')}
        description={t('admin.settings.faces.forgetText')}
        confirmLabel={t('admin.settings.faces.forget')}
        cancelLabel={t('common.cancel')}
        closeLabel={t('common.close')}
        destructive
        pending={forget.isPending}
        onConfirm={async () => {
          await forget.mutateAsync()
        }}
      />
      {result && (
        <p role="status" className="text-base text-muted-foreground">
          {t('admin.settings.faces.forgotten', { faces: result.faces, persons: result.persons })}
        </p>
      )}
      {forget.isError && (
        <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>
      )}
    </div>
  )
}

function draftOf(settings: AppSettings): Draft {
  return Object.fromEntries(
    Object.keys(LIMITS).map((setting) => [setting, String(settings[setting as NumericSetting])]),
  ) as Draft
}

function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')
  return failure.problem.detail ?? t('auth.error.unexpected')
}
