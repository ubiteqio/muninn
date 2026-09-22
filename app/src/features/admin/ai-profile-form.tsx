import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isApiError, type Problem } from '@/api/problem'
import { Button } from '@/components/ui/button'
import {
  type AiKind,
  type AiProfile,
  useCreateAiProfile,
  useSaveAiProfile,
} from '@/features/admin/use-ai'
import { Field } from '@/features/auth/field'
import { FormError } from '@/features/auth/form-error'

interface AiProfileFormProps {
  kind: AiKind
  /** Given when an existing machine is being changed rather than a new one set up. */
  profile?: AiProfile
  onDone: () => void
}

/**
 * Setting up one machine.
 *
 * The key is write-only: it is never sent back to the browser, and leaving the field empty
 * keeps the one that is stored. Nobody should have to retype a secret to change a timeout.
 */
export function AiProfileForm({ kind, profile, onDone }: AiProfileFormProps) {
  const { t } = useTranslation()
  const create = useCreateAiProfile()
  const save = useSaveAiProfile()

  const [name, setName] = useState(profile?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(profile?.base_url ?? '')
  const [model, setModel] = useState(profile?.model ?? '')
  const [apiKey, setApiKey] = useState('')
  const [concurrency, setConcurrency] = useState(String(profile?.concurrency ?? 2))
  const [timeout, setTimeout] = useState(String(profile?.timeout_seconds ?? 120))
  const [error, setError] = useState<string | null>(null)

  const pending = create.isPending || save.isPending

  async function submit() {
    setError(null)

    try {
      if (profile) {
        await save.mutateAsync({
          id: profile.id,
          changes: {
            name,
            base_url: baseUrl,
            model,
            concurrency: Number(concurrency),
            timeout_seconds: Number(timeout),
            // Empty means "leave the stored one alone", which is what the API does with null.
            ...(apiKey ? { api_key: apiKey } : {}),
          },
        })
      } else {
        await create.mutateAsync({
          kind,
          name,
          base_url: baseUrl,
          model,
          api_key: apiKey,
          concurrency: Number(concurrency),
          timeout_seconds: Number(timeout),
        })
      }
      onDone()
    } catch (failure) {
      setError(messageFor(failure, t))
    }
  }

  return (
    <form
      className="space-y-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <Field
        label={t('admin.ai.field.name')}
        value={name}
        onChange={(event) => {
          setName(event.target.value)
        }}
        placeholder={t('admin.ai.placeholder.name')}
        required
      />
      <Field
        label={t('admin.ai.field.baseUrl')}
        hint={t('admin.ai.hint.baseUrl')}
        value={baseUrl}
        onChange={(event) => {
          setBaseUrl(event.target.value)
        }}
        placeholder="http://gpu.zuhause:8000/v1"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        required
      />
      <Field
        label={t('admin.ai.field.model')}
        hint={t('admin.ai.hint.model')}
        value={model}
        onChange={(event) => {
          setModel(event.target.value)
        }}
        placeholder="Qwen3-VL-8B-Instruct"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        required
      />
      <Field
        label={t('admin.ai.field.apiKey')}
        hint={t(profile?.has_api_key ? 'admin.ai.hint.keyStored' : 'admin.ai.hint.apiKey')}
        type="password"
        value={apiKey}
        onChange={(event) => {
          setApiKey(event.target.value)
        }}
        autoComplete="off"
      />

      <div className="grid grid-cols-2 gap-4">
        <Field
          label={t('admin.ai.field.concurrency')}
          hint={t('admin.ai.hint.concurrency')}
          type="number"
          min={1}
          max={32}
          value={concurrency}
          onChange={(event) => {
            setConcurrency(event.target.value)
          }}
        />
        <Field
          label={t('admin.ai.field.timeout')}
          hint={t('admin.ai.hint.timeout')}
          type="number"
          min={5}
          max={1800}
          value={timeout}
          onChange={(event) => {
            setTimeout(event.target.value)
          }}
        />
      </div>

      <FormError message={error} />

      <div className="flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? t('admin.ai.saving') : t('admin.ai.save')}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          {t('admin.ai.cancel')}
        </Button>
      </div>
    </form>
  )
}

/** What the API calls a field, and what the form calls it. */
const FIELD_LABELS: Record<string, string> = {
  name: 'name',
  base_url: 'baseUrl',
  model: 'model',
  api_key: 'apiKey',
  concurrency: 'concurrency',
  timeout_seconds: 'timeout',
}

/**
 * Why the machine was not saved, in words.
 *
 * A rejected form should say which field it is about. The API sends that - one entry per field
 * it refused - and a sentence that only says "please check your input" makes somebody hunt
 * through six fields for the one that is wrong.
 */
function messageFor(failure: unknown, t: TFunction): string {
  if (!isApiError(failure)) return t('auth.error.unreachable')

  const fields = refusedFields(failure.problem).map((field) => t(`admin.ai.field.${field}`))
  if (fields.length > 0) return t('admin.ai.invalidFields', { fields: fields.join(', ') })

  return failure.problem.detail ?? t('admin.ai.invalid')
}

function refusedFields(problem: Problem): string[] {
  const errors = problem.errors
  if (!Array.isArray(errors)) return []

  const fields = new Set<string>()
  for (const entry of errors) {
    if (!entry || typeof entry !== 'object') continue
    const where = (entry as { location?: unknown }).location
    const field = Array.isArray(where) ? String(where.at(-1)) : ''
    const label = FIELD_LABELS[field]
    if (label) fields.add(label)
  }
  return [...fields]
}
